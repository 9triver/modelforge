import { useEffect, useRef, useState } from 'react';
import { getCalibration, listDatasetRepos, postCalibrationPreview, saveCalibration } from '../lib/api';
import type { CalibrationRecord, SearchResult } from '../lib/types';
import DatasetUpload from './DatasetUpload';

function fmt(v: number | null | undefined): string {
  if (v == null) return '—';
  if (Math.abs(v) >= 100) return v.toFixed(2);
  if (Math.abs(v) >= 1) return v.toFixed(3);
  return v.toFixed(4);
}

const ALL_METHODS = [
  { id: 'linear_bias', label: 'Linear Bias', desc: '全局 y = a·pred + b' },
  { id: 'segmented', label: 'Segmented', desc: '按时段分 4 段，各自 (a, b)' },
  { id: 'stacking', label: 'Stacking', desc: 'GBR 残差模型（需要 sklearn）' },
] as const;

type MethodId = (typeof ALL_METHODS)[number]['id'];

const STATUS_COLOR: Record<string, string> = {
  queued: 'bg-gray-100 text-gray-700',
  running: 'bg-amber-100 text-amber-800',
  previewed: 'bg-blue-100 text-blue-800',
  saving: 'bg-amber-100 text-amber-800',
  ok: 'bg-green-100 text-green-800',
  error: 'bg-red-100 text-red-800',
};

type Props = {
  namespace: string;
  name: string;
  revision: string;
  task: string | null;
};

export default function CalibrateTab({ namespace, name, revision, task }: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [datasetRepo, setDatasetRepo] = useState<string | null>(null);
  const [datasetRepos, setDatasetRepos] = useState<SearchResult[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  // multi-method preview results
  const [results, setResults] = useState<Map<MethodId, CalibrationRecord>>(new Map());
  const [selected, setSelected] = useState<MethodId | null>(null);

  // save phase
  const [targetNs, setTargetNs] = useState('');
  const [targetName, setTargetName] = useState('');
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [savedRec, setSavedRec] = useState<CalibrationRecord | null>(null);

  const pollRefs = useRef<Map<number, number>>(new Map());

  useEffect(() => {
    setTargetNs(namespace);
    setTargetName(`${name}-calibrated`);
  }, [namespace, name]);

  useEffect(() => {
    return () => { pollRefs.current.forEach((t) => clearInterval(t)); };
  }, []);

  useEffect(() => {
    listDatasetRepos('csv').then(setDatasetRepos).catch(() => {});
  }, []);

  if (task !== 'time-series-forecasting') {
    return (
      <div className="bg-yellow-50 text-yellow-800 p-4 rounded text-sm">
        校准目前仅支持 time-series-forecasting task。
      </div>
    );
  }

  const pollOne = (id: number, method: MethodId) => {
    const t = window.setInterval(async () => {
      try {
        const rec = await getCalibration(id);
        setResults((prev) => new Map(prev).set(method, rec));
        if (rec.status === 'previewed' || rec.status === 'error') {
          clearInterval(t);
          pollRefs.current.delete(id);
        }
      } catch { /* retry */ }
    }, 1000);
    pollRefs.current.set(id, t);
  };

  const runPreviewAll = async () => {
    if (!file && !datasetRepo) return;
    setSubmitError(null);
    setSubmitting(true);
    setResults(new Map());
    setSelected(null);
    setSavedRec(null);
    try {
      for (const m of ALL_METHODS) {
        const { calibration_id } = await postCalibrationPreview(
          namespace, name, file, revision, m.id, datasetRepo || undefined,
        );
        const rec = await getCalibration(calibration_id);
        setResults((prev) => new Map(prev).set(m.id, rec));
        pollOne(calibration_id, m.id);
      }
    } catch (e: any) {
      setSubmitError(e.message || String(e));
    } finally {
      setSubmitting(false);
    }
  };

  const doSave = async () => {
    if (!selected || !targetNs || !targetName) return;
    const rec = results.get(selected);
    if (!rec) return;
    setSaveError(null);
    setSaving(true);
    try {
      await saveCalibration(rec.id, targetNs, targetName);
      const pollSave = window.setInterval(async () => {
        const r = await getCalibration(rec.id);
        if (r.status === 'ok' || r.status === 'error') {
          clearInterval(pollSave);
          setSavedRec(r);
          setSaving(false);
        }
      }, 1000);
    } catch (e: any) {
      setSaveError(e.message || String(e));
      setSaving(false);
    }
  };

  const reset = () => {
    pollRefs.current.forEach((t) => clearInterval(t));
    pollRefs.current.clear();
    setResults(new Map());
    setSelected(null);
    setFile(null);
    setSubmitError(null);
    setSaveError(null);
    setSavedRec(null);
  };

  const allDone = results.size === ALL_METHODS.length &&
    [...results.values()].every((r) => r.status === 'previewed' || r.status === 'error');
  const anyRunning = [...results.values()].some((r) => r.status === 'queued' || r.status === 'running');
  const beforeMetrics = [...results.values()].find((r) => r.before_metrics)?.before_metrics;

  // ---------- saved view ----------
  if (savedRec && savedRec.status === 'ok' && savedRec.target_repo) {
    return (
      <div className="border border-green-200 rounded-lg bg-white p-4 space-y-3">
        <div className="text-green-700 font-medium">校准模型已保存</div>
        <div className="text-sm">
          方法: <code className="bg-gray-100 px-1 rounded">{savedRec.method}</code>
        </div>
        <div className="text-sm">
          已保存到 <a href={`/${savedRec.target_repo}`} className="text-blue-600 hover:underline font-medium">{savedRec.target_repo}</a>
        </div>
        <button onClick={reset} className="px-3 py-1.5 text-sm border border-gray-300 rounded hover:bg-gray-50">
          Run another
        </button>
      </div>
    );
  }

  // ---------- compare view ----------
  if (results.size > 0) {
    return (
      <div className="space-y-4">
        {anyRunning && (
          <div className="text-sm text-gray-600 flex items-center gap-2">
            <span className="inline-block w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
            正在校准…
          </div>
        )}

        <table className="w-full text-sm border border-gray-200 rounded overflow-hidden">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-3 py-2 text-left text-xs text-gray-500 w-8"></th>
              <th className="px-3 py-2 text-left text-xs text-gray-500">Method</th>
              <th className="px-3 py-2 text-right text-xs text-gray-500">Before MAPE</th>
              <th className="px-3 py-2 text-right text-xs text-gray-500">After MAPE</th>
              <th className="px-3 py-2 text-right text-xs text-gray-500">After RMSE</th>
              <th className="px-3 py-2 text-right text-xs text-gray-500">After MAE</th>
              <th className="px-3 py-2 text-center text-xs text-gray-500">Status</th>
            </tr>
          </thead>
          <tbody>
            {ALL_METHODS.map((m) => {
              const rec = results.get(m.id);
              const isPreviewed = rec?.status === 'previewed';
              return (
                <tr
                  key={m.id}
                  className={`border-t border-gray-200 cursor-pointer ${
                    selected === m.id ? 'bg-blue-50' : 'hover:bg-gray-50'
                  }`}
                  onClick={() => isPreviewed && setSelected(m.id)}
                >
                  <td className="px-3 py-2 text-center">
                    {isPreviewed && (
                      <input
                        type="radio"
                        name="cal-method"
                        checked={selected === m.id}
                        onChange={() => setSelected(m.id)}
                        className="accent-blue-600"
                      />
                    )}
                  </td>
                  <td className="px-3 py-2">
                    <div className="font-medium">{m.label}</div>
                    <div className="text-xs text-gray-500">{m.desc}</div>
                  </td>
                  <td className="px-3 py-2 text-right font-mono">
                    {fmt(rec?.before_value ?? beforeMetrics?.mape)}
                  </td>
                  <td className="px-3 py-2 text-right font-mono font-semibold">
                    {isPreviewed ? fmt(rec?.after_value) : '—'}
                  </td>
                  <td className="px-3 py-2 text-right font-mono">
                    {isPreviewed ? fmt(rec?.after_metrics?.rmse) : '—'}
                  </td>
                  <td className="px-3 py-2 text-right font-mono">
                    {isPreviewed ? fmt(rec?.after_metrics?.mae) : '—'}
                  </td>
                  <td className="px-3 py-2 text-center">
                    {rec ? (
                      <span className={`text-xs px-1.5 py-0.5 rounded ${STATUS_COLOR[rec.status] || ''}`}>
                        {rec.status === 'previewed' ? 'ready' : rec.status}
                      </span>
                    ) : (
                      <span className="text-xs text-gray-400">—</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>

        {allDone && selected && (
          <div className="border-t border-gray-200 pt-3 space-y-3">
            <div className="text-sm font-medium text-gray-700">
              选择了 <code className="bg-gray-100 px-1 rounded">{selected}</code>，保存为新模型
            </div>
            <div className="flex items-center gap-2 text-sm">
              <span className="text-gray-500">Fork to:</span>
              <input
                value={targetNs}
                onChange={(e) => setTargetNs(e.target.value)}
                className="border border-gray-300 rounded px-2 py-1 w-32 text-sm"
              />
              <span className="text-gray-400">/</span>
              <input
                value={targetName}
                onChange={(e) => setTargetName(e.target.value)}
                className="border border-gray-300 rounded px-2 py-1 w-64 text-sm"
              />
            </div>
            <div className="flex gap-2">
              <button
                disabled={!targetNs || !targetName || saving}
                onClick={doSave}
                className="px-4 py-2 rounded bg-green-600 text-white text-sm font-medium disabled:bg-gray-300"
              >
                {saving ? '保存中…' : 'Save as new model'}
              </button>
              <button onClick={reset} className="px-3 py-1.5 text-sm border border-gray-300 rounded hover:bg-gray-50">
                Start over
              </button>
            </div>
            {saveError && <pre className="bg-red-50 text-red-800 p-2 rounded text-xs">{saveError}</pre>}
          </div>
        )}

        {allDone && !selected && (
          <div className="flex gap-2">
            <div className="text-sm text-gray-500">选择一个方法后可保存为新模型</div>
            <button onClick={reset} className="px-3 py-1.5 text-sm border border-gray-300 rounded hover:bg-gray-50">
              Start over
            </button>
          </div>
        )}
      </div>
    );
  }

  // ---------- upload view ----------
  return (
    <div className="space-y-4">
      <div className="text-sm text-gray-600">
        上传目标区域数据，同时预览三种校准方法的效果，选最好的保存为新模型。
      </div>
      <DatasetUpload
        onFile={(f) => { setFile(f); setDatasetRepo(null); }}
        onDatasetRepo={(r) => { setDatasetRepo(r); setFile(null); }}
        datasetRepos={datasetRepos}
        disabled={submitting}
        hint="CSV / Parquet — 目标区域数据（timestamp + target 列，建议 1-2 周）"
      />
      <div className="flex items-center justify-between text-sm">
        <span className="text-gray-600">
          Revision: <code className="bg-gray-100 px-1 rounded">{revision}</code>
        </span>
        <button
          disabled={(!file && !datasetRepo) || submitting}
          onClick={runPreviewAll}
          className="px-4 py-2 rounded bg-blue-600 text-white text-sm font-medium disabled:bg-gray-300"
        >
          {submitting ? '提交中…' : 'Preview all methods'}
        </button>
      </div>
      {submitError && (
        <pre className="bg-red-50 text-red-800 p-3 rounded text-xs whitespace-pre-wrap">{submitError}</pre>
      )}
    </div>
  );
}
