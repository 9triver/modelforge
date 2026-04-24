import { useEffect, useRef, useState } from 'react';
import { getEvaluation, listDatasetRepos, postEvaluation } from '../lib/api';
import type { Evaluation, SearchResult } from '../lib/types';
import DatasetUpload from './DatasetUpload';
import EvaluationStatus from './EvaluationStatus';

const SUPPORTED: Record<string, { hint: string; formats: string[] }> = {
  'time-series-forecasting': {
    hint: 'CSV / Parquet — 必含 timestamp 列 + model card 声明的 target/features',
    formats: ['csv', 'parquet'],
  },
  'image-classification': {
    hint: 'ZIP — ImageFolder 结构（每个类别一个子目录，子目录里放图片）',
    formats: ['image_folder'],
  },
  'object-detection': {
    hint: 'ZIP — 含 images/ 目录 + annotations.json（COCO 格式）',
    formats: ['coco_json'],
  },
};

type Props = {
  namespace: string;
  name: string;
  revision: string;
  task: string | null;
  onDone: () => void;
  onCalibrate?: () => void;
};

export default function EvaluateTab({ namespace, name, revision, task, onDone, onCalibrate }: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [datasetRepo, setDatasetRepo] = useState<string | null>(null);
  const [datasetRepos, setDatasetRepos] = useState<SearchResult[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [evalRec, setEvalRec] = useState<Evaluation | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const pollRef = useRef<number | null>(null);

  const supported = task ? task in SUPPORTED : false;
  const hint = task && supported ? SUPPORTED[task].hint : '';

  useEffect(() => {
    if (task && supported) {
      const formats = SUPPORTED[task].formats;
      Promise.all(formats.map((f) => listDatasetRepos(f)))
        .then((results) => setDatasetRepos(results.flat()))
        .catch(() => {});
    }
    return () => {
      if (pollRef.current != null) clearInterval(pollRef.current);
    };
  }, [task, supported]);

  const startPolling = (id: number) => {
    if (pollRef.current != null) clearInterval(pollRef.current);
    pollRef.current = window.setInterval(async () => {
      try {
        const rec = await getEvaluation(id);
        setEvalRec(rec);
        if (rec.status === 'ok' || rec.status === 'error') {
          if (pollRef.current != null) {
            clearInterval(pollRef.current);
            pollRef.current = null;
          }
        }
      } catch (e) {
        // 保留上次记录，下一次再试
        console.error(e);
      }
    }, 1000);
  };

  const run = async () => {
    if (!file && !datasetRepo) return;
    setSubmitError(null);
    setSubmitting(true);
    try {
      const { evaluation_id } = await postEvaluation(namespace, name, file, revision, datasetRepo || undefined);
      const rec = await getEvaluation(evaluation_id);
      setEvalRec(rec);
      startPolling(evaluation_id);
    } catch (e: any) {
      setSubmitError(e.message || String(e));
    } finally {
      setSubmitting(false);
    }
  };

  const reset = () => {
    if (pollRef.current != null) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    setEvalRec(null);
    setFile(null);
    setDatasetRepo(null);
    setSubmitError(null);
  };

  if (!task) {
    return (
      <div className="bg-yellow-50 text-yellow-800 p-4 rounded text-sm">
        model_card.yaml 未声明 pipeline_tag，无法评估。
      </div>
    );
  }

  if (!supported) {
    return (
      <div className="bg-yellow-50 text-yellow-800 p-4 rounded text-sm">
        task <code className="bg-yellow-100 px-1 rounded">{task}</code> 暂不支持评估。
        <div className="mt-1 text-xs text-yellow-700">
          已支持：{Object.keys(SUPPORTED).join(', ')}
        </div>
      </div>
    );
  }

  if (evalRec) {
    return (
      <EvaluationStatus
        evalRec={evalRec}
        onReset={reset}
        onViewPerformance={onDone}
        onCalibrate={onCalibrate}
      />
    );
  }

  return (
    <div className="space-y-4">
      <DatasetUpload
        onFile={(f) => { setFile(f); setDatasetRepo(null); }}
        onDatasetRepo={(r) => { setDatasetRepo(r); setFile(null); }}
        datasetRepos={datasetRepos}
        disabled={submitting}
        hint={hint}
      />

      <div className="flex items-center justify-between text-sm">
        <div className="text-gray-600 space-x-3">
          <span>Task: <code className="bg-gray-100 px-1 rounded">{task}</code></span>
          <span>Revision: <code className="bg-gray-100 px-1 rounded">{revision}</code></span>
        </div>
        <button
          disabled={(!file && !datasetRepo) || submitting}
          onClick={run}
          className="px-4 py-2 rounded bg-blue-600 text-white text-sm font-medium disabled:bg-gray-300"
        >
          {submitting ? '提交中…' : 'Run evaluation'}
        </button>
      </div>

      {submitError && (
        <pre className="bg-red-50 text-red-800 p-3 rounded text-xs whitespace-pre-wrap">
          {submitError}
        </pre>
      )}
    </div>
  );
}
