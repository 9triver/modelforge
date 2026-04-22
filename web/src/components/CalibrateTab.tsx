import { useEffect, useRef, useState } from 'react';
import { getCalibration, postCalibrationPreview, saveCalibration } from '../lib/api';
import type { CalibrationRecord } from '../lib/types';
import DatasetUpload from './DatasetUpload';

function fmt(v: number | null | undefined): string {
  if (v == null) return '—';
  if (Math.abs(v) >= 100) return v.toFixed(2);
  if (Math.abs(v) >= 1) return v.toFixed(3);
  return v.toFixed(4);
}

const STATUS_COLOR: Record<string, string> = {
  queued: 'bg-gray-100 text-gray-700',
  running: 'bg-amber-100 text-amber-800',
  previewed: 'bg-blue-100 text-blue-800',
  saving: 'bg-amber-100 text-amber-800',
  ok: 'bg-green-100 text-green-800',
  error: 'bg-red-100 text-red-800',
};

const STATUS_LABEL: Record<string, string> = {
  queued: 'queued',
  running: 'running',
  previewed: 'preview ready',
  saving: 'saving...',
  ok: 'saved',
  error: 'failed',
};

type Props = {
  namespace: string;
  name: string;
  revision: string;
  task: string | null;
};

export default function CalibrateTab({ namespace, name, revision, task }: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [calRec, setCalRec] = useState<CalibrationRecord | null>(null);

  // save phase
  const [targetNs, setTargetNs] = useState('');
  const [targetName, setTargetName] = useState('');
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const pollRef = useRef<number | null>(null);

  useEffect(() => {
    setTargetNs(namespace);
    setTargetName(`${name}-calibrated`);
  }, [namespace, name]);

  useEffect(() => {
    return () => { if (pollRef.current != null) clearInterval(pollRef.current); };
  }, []);

  if (task !== 'time-series-forecasting') {
    return (
      <div className="bg-yellow-50 text-yellow-800 p-4 rounded text-sm">
        校准目前仅支持 time-series-forecasting task。
      </div>
    );
  }

  const startPolling = (id: number, until: string[]) => {
    if (pollRef.current != null) clearInterval(pollRef.current);
    pollRef.current = window.setInterval(async () => {
      try {
        const rec = await getCalibration(id);
        setCalRec(rec);
        if (until.includes(rec.status)) {
          if (pollRef.current != null) { clearInterval(pollRef.current); pollRef.current = null; }
        }
      } catch { /* retry */ }
    }, 1000);
  };

  const runPreview = async () => {
    if (!file) return;
    setSubmitError(null);
    setSubmitting(true);
    try {
      const { calibration_id } = await postCalibrationPreview(namespace, name, file, revision);
      const rec = await getCalibration(calibration_id);
      setCalRec(rec);
      startPolling(calibration_id, ['previewed', 'error']);
    } catch (e: any) {
      setSubmitError(e.message || String(e));
    } finally {
      setSubmitting(false);
    }
  };

  const doSave = async () => {
    if (!calRec || !targetNs || !targetName) return;
    setSaveError(null);
    setSaving(true);
    try {
      await saveCalibration(calRec.id, targetNs, targetName);
      startPolling(calRec.id, ['ok', 'error']);
    } catch (e: any) {
      setSaveError(e.message || String(e));
    } finally {
      setSaving(false);
    }
  };

  const reset = () => {
    if (pollRef.current != null) { clearInterval(pollRef.current); pollRef.current = null; }
    setCalRec(null);
    setFile(null);
    setSubmitError(null);
    setSaveError(null);
  };

  // ---------- result / status view ----------
  if (calRec) {
    const { id, status, method, params, before_metrics, after_metrics,
            primary_metric, target_repo, duration_ms, error } = calRec;

    return (
      <div className="border border-gray-200 rounded-lg bg-white overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-200 flex items-center justify-between">
          <div className="font-medium">Calibration #{id}</div>
          <span className={`text-xs font-semibold px-2 py-0.5 rounded ${STATUS_COLOR[status] || ''}`}>
            {STATUS_LABEL[status] || status}
          </span>
        </div>

        <div className="p-4 space-y-3">
          {(status === 'queued' || status === 'running') && (
            <div className="text-sm text-gray-600 flex items-center gap-2">
              <span className="inline-block w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
              {status === 'queued' ? '排队中…' : '正在校准…'}
            </div>
          )}

          {status === 'saving' && (
            <div className="text-sm text-gray-600 flex items-center gap-2">
              <span className="inline-block w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
              正在创建 fork 仓库…
            </div>
          )}

          {/* previewed or ok: show before/after table */}
          {(status === 'previewed' || status === 'ok') && before_metrics && after_metrics && (
            <>
              <div className="text-sm text-gray-600">
                Method: <code className="bg-gray-100 px-1 rounded">{method}</code>
                {params && <span className="ml-2">a={params.a}, b={fmt(params.b)}</span>}
              </div>
              <table className="w-full text-sm border border-gray-200 rounded">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-3 py-2 text-left text-xs text-gray-500">Metric</th>
                    <th className="px-3 py-2 text-right text-xs text-gray-500">Before</th>
                    <th className="px-3 py-2 text-right text-xs text-gray-500">After</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.keys(before_metrics).map((k) => (
                    <tr key={k} className={k === primary_metric ? 'bg-blue-50 font-semibold' : ''}>
                      <td className="px-3 py-1.5 text-gray-600 uppercase text-xs">{k}</td>
                      <td className="px-3 py-1.5 text-right font-mono">{fmt(before_metrics[k])}</td>
                      <td className="px-3 py-1.5 text-right font-mono">{fmt(after_metrics[k])}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {duration_ms != null && (
                <div className="text-xs text-gray-500">Duration: {(duration_ms / 1000).toFixed(2)}s</div>
              )}
            </>
          )}

          {/* previewed: show save form */}
          {status === 'previewed' && (
            <div className="border-t border-gray-200 pt-3 mt-3 space-y-3">
              <div className="text-sm font-medium text-gray-700">满意？保存为新模型</div>
              <div className="flex items-center gap-2 text-sm">
                <span className="text-gray-500">Fork to:</span>
                <input
                  value={targetNs}
                  onChange={(e) => setTargetNs(e.target.value)}
                  className="border border-gray-300 rounded px-2 py-1 w-32 text-sm"
                  placeholder="namespace"
                />
                <span className="text-gray-400">/</span>
                <input
                  value={targetName}
                  onChange={(e) => setTargetName(e.target.value)}
                  className="border border-gray-300 rounded px-2 py-1 w-64 text-sm"
                  placeholder="name"
                />
              </div>
              <button
                disabled={!targetNs || !targetName || saving}
                onClick={doSave}
                className="px-4 py-2 rounded bg-green-600 text-white text-sm font-medium disabled:bg-gray-300"
              >
                {saving ? '保存中…' : 'Save as new model'}
              </button>
              {saveError && (
                <pre className="bg-red-50 text-red-800 p-2 rounded text-xs">{saveError}</pre>
              )}
            </div>
          )}

          {/* ok: show fork link */}
          {status === 'ok' && target_repo && (
            <div className="border-t border-gray-200 pt-3 mt-3">
              <div className="text-sm text-green-700 font-medium">
                已保存到 <a href={`/${target_repo}`} className="text-blue-600 hover:underline">{target_repo}</a>
              </div>
            </div>
          )}

          {status === 'error' && (
            <pre className="bg-red-50 text-red-800 p-3 rounded text-xs whitespace-pre-wrap break-words">
              {error || 'unknown error'}
            </pre>
          )}
        </div>

        <div className="px-4 py-3 bg-gray-50 border-t border-gray-200">
          <button
            onClick={reset}
            className="px-3 py-1.5 text-sm border border-gray-300 rounded hover:bg-white"
          >
            {status === 'ok' ? 'Run another' : status === 'error' ? 'Try again' : 'Start over'}
          </button>
        </div>
      </div>
    );
  }

  // ---------- upload view ----------
  return (
    <div className="space-y-4">
      <div className="text-sm text-gray-600">
        上传目标区域数据，预览校准效果。满意后再保存为新模型。
      </div>
      <DatasetUpload
        onFile={setFile}
        disabled={submitting}
        hint="CSV / Parquet — 目标区域数据（timestamp + target 列，建议 1-2 周）"
      />
      <div className="flex items-center justify-between text-sm">
        <span className="text-gray-600">
          Revision: <code className="bg-gray-100 px-1 rounded">{revision}</code>
        </span>
        <button
          disabled={!file || submitting}
          onClick={runPreview}
          className="px-4 py-2 rounded bg-blue-600 text-white text-sm font-medium disabled:bg-gray-300"
        >
          {submitting ? '提交中…' : 'Preview calibration'}
        </button>
      </div>
      {submitError && (
        <pre className="bg-red-50 text-red-800 p-3 rounded text-xs whitespace-pre-wrap">{submitError}</pre>
      )}
    </div>
  );
}
