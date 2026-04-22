import { useEffect, useRef, useState } from 'react';
import { getTransfer, postTransferPreview, saveTransfer } from '../lib/api';
import type { TransferRecord } from '../lib/types';
import DatasetUpload from './DatasetUpload';

function fmt(v: number | null | undefined): string {
  if (v == null) return '—';
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

type Props = {
  namespace: string;
  name: string;
  revision: string;
  task: string | null;
};

export default function TransferTab({ namespace, name, revision, task }: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [rec, setRec] = useState<TransferRecord | null>(null);

  const [targetNs, setTargetNs] = useState('');
  const [targetName, setTargetName] = useState('');
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [savedRec, setSavedRec] = useState<TransferRecord | null>(null);

  const pollRef = useRef<number | null>(null);

  useEffect(() => {
    setTargetNs(namespace);
    setTargetName(`${name}-transferred`);
  }, [namespace, name]);

  useEffect(() => {
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, []);

  if (task !== 'image-classification') {
    return (
      <div className="bg-yellow-50 text-yellow-800 p-4 rounded text-sm">
        迁移学习目前仅支持 image-classification task。
      </div>
    );
  }

  const pollOne = (id: number) => {
    pollRef.current = window.setInterval(async () => {
      try {
        const r = await getTransfer(id);
        setRec(r);
        if (r.status === 'previewed' || r.status === 'error') {
          if (pollRef.current) clearInterval(pollRef.current);
          pollRef.current = null;
        }
      } catch { /* retry */ }
    }, 1000);
  };

  const runPreview = async () => {
    if (!file) return;
    setSubmitError(null);
    setSubmitting(true);
    setRec(null);
    setSavedRec(null);
    try {
      const { transfer_id } = await postTransferPreview(namespace, name, file, revision);
      const r = await getTransfer(transfer_id);
      setRec(r);
      pollOne(transfer_id);
    } catch (e: any) {
      setSubmitError(e.message || String(e));
    } finally {
      setSubmitting(false);
    }
  };

  const doSave = async () => {
    if (!rec || !targetNs || !targetName) return;
    setSaveError(null);
    setSaving(true);
    try {
      await saveTransfer(rec.id, targetNs, targetName);
      const pollSave = window.setInterval(async () => {
        const r = await getTransfer(rec.id);
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
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = null;
    setRec(null);
    setFile(null);
    setSubmitError(null);
    setSaveError(null);
    setSavedRec(null);
  };

  // ---------- saved view ----------
  if (savedRec && savedRec.status === 'ok' && savedRec.target_repo) {
    return (
      <div className="border border-green-200 rounded-lg bg-white p-4 space-y-3">
        <div className="text-green-700 font-medium">迁移模型已保存</div>
        <div className="text-sm">
          方法: <code className="bg-gray-100 px-1 rounded">{savedRec.method}</code>
          · {savedRec.n_classes} 个类别 · {savedRec.n_samples} 个样本
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

  // ---------- preview result ----------
  if (rec) {
    const isPreviewed = rec.status === 'previewed';
    const isRunning = rec.status === 'queued' || rec.status === 'running';

    return (
      <div className="space-y-4">
        {isRunning && (
          <div className="text-sm text-gray-600 flex items-center gap-2">
            <span className="inline-block w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
            正在提取特征并训练分类头…
          </div>
        )}

        {rec.status === 'error' && (
          <pre className="bg-red-50 text-red-800 p-3 rounded text-xs whitespace-pre-wrap">{rec.error}</pre>
        )}

        {isPreviewed && rec.after_metrics && (
          <div className="space-y-3">
            <div className="text-sm text-gray-700">
              Linear probe: <span className="font-medium">{rec.n_classes} 个类别</span>
              {rec.classes && (
                <span className="text-gray-500 ml-1">({rec.classes.join(', ')})</span>
              )}
              · {rec.n_samples} 个样本
            </div>

            <table className="w-full text-sm border border-gray-200 rounded overflow-hidden">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-3 py-2 text-left text-xs text-gray-500">Metric</th>
                  <th className="px-3 py-2 text-right text-xs text-gray-500">Value</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(rec.after_metrics).map(([k, v]) => (
                  <tr key={k} className={`border-t border-gray-200 ${k === rec.primary_metric ? 'bg-blue-50 font-semibold' : ''}`}>
                    <td className="px-3 py-2">{k}</td>
                    <td className="px-3 py-2 text-right font-mono">{fmt(v)}</td>
                  </tr>
                ))}
              </tbody>
            </table>

            <div className="border-t border-gray-200 pt-3 space-y-3">
              <div className="text-sm font-medium text-gray-700">保存为新模型</div>
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
          </div>
        )}

        {!isPreviewed && !isRunning && rec.status !== 'error' && (
          <div className="text-sm text-gray-500">
            <span className={`text-xs px-1.5 py-0.5 rounded ${STATUS_COLOR[rec.status] || ''}`}>
              {rec.status}
            </span>
          </div>
        )}
      </div>
    );
  }

  // ---------- upload view ----------
  return (
    <div className="space-y-4">
      <div className="text-sm text-gray-600 space-y-1">
        <div>
          <strong>Linear Probe</strong>：冻结 base 模型 backbone，提取倒数第二层特征，训练 sklearn 线性分类头。
        </div>
        <div className="text-gray-500">
          Base 模型权重不修改 — fork 出的新仓库仅包含新分类头（几 KB），推理时通过
          <code className="bg-gray-100 px-1 rounded mx-1">base.extract_features()</code>
          调用 base 模型。
        </div>
      </div>
      <DatasetUpload
        onFile={setFile}
        disabled={submitting}
        hint="ZIP — ImageFolder 格式（class_name/xxx.jpg），每类至少 4 张"
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
          {submitting ? '提交中…' : 'Preview transfer'}
        </button>
      </div>
      {submitError && (
        <pre className="bg-red-50 text-red-800 p-3 rounded text-xs whitespace-pre-wrap">{submitError}</pre>
      )}
    </div>
  );
}
