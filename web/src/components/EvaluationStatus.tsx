import type { Evaluation } from '../lib/types';

function fmt(v: number | null | undefined): string {
  if (v == null) return '—';
  if (Math.abs(v) >= 100) return v.toFixed(2);
  if (Math.abs(v) >= 1) return v.toFixed(3);
  return v.toFixed(4);
}

const STATUS_LABEL: Record<Evaluation['status'], string> = {
  queued: 'queued',
  running: 'running',
  ok: 'ok',
  error: 'failed',
};

const STATUS_COLOR: Record<Evaluation['status'], string> = {
  queued: 'bg-gray-100 text-gray-700',
  running: 'bg-amber-100 text-amber-800',
  ok: 'bg-green-100 text-green-800',
  error: 'bg-red-100 text-red-800',
};

export default function EvaluationStatus({
  evalRec,
  onReset,
  onViewPerformance,
  onCalibrate,
}: {
  evalRec: Evaluation;
  onReset: () => void;
  onViewPerformance: () => void;
  onCalibrate?: () => void;
}) {
  const { id, status, metrics, primary_metric, duration_ms, error } = evalRec;

  return (
    <div className="border border-gray-200 rounded-lg bg-white overflow-hidden">
      <div className="px-4 py-3 border-b border-gray-200 flex items-center justify-between">
        <div className="font-medium">Evaluation #{id}</div>
        <span className={`text-xs font-semibold px-2 py-0.5 rounded ${STATUS_COLOR[status]}`}>
          {STATUS_LABEL[status]}
        </span>
      </div>

      <div className="p-4 space-y-3">
        {(status === 'queued' || status === 'running') && (
          <div className="text-sm text-gray-600 flex items-center gap-2">
            <span className="inline-block w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
            {status === 'queued' ? '排队中…' : '正在评估…'}
          </div>
        )}

        {status === 'ok' && metrics && (
          <>
            <table className="w-full text-sm">
              <tbody>
                {Object.entries(metrics).map(([k, v]) => (
                  <tr
                    key={k}
                    className={k === primary_metric ? 'bg-blue-50 font-semibold' : ''}
                  >
                    <td className="py-1.5 px-2 text-gray-600 uppercase text-xs tracking-wide">
                      {k}
                      {k === primary_metric && (
                        <span className="ml-1 text-blue-600 normal-case tracking-normal">
                          · primary
                        </span>
                      )}
                    </td>
                    <td className="py-1.5 px-2 font-mono text-right">{fmt(v)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="text-xs text-gray-500">
              Duration: {duration_ms != null ? `${(duration_ms / 1000).toFixed(2)}s` : '—'}
            </div>
          </>
        )}

        {status === 'error' && (
          <pre className="bg-red-50 text-red-800 p-3 rounded text-xs whitespace-pre-wrap break-words">
            {error || 'unknown error'}
          </pre>
        )}
      </div>

      <div className="px-4 py-3 bg-gray-50 border-t border-gray-200 flex items-center gap-3">
        <button
          onClick={onReset}
          className="px-3 py-1.5 text-sm border border-gray-300 rounded hover:bg-white"
        >
          {status === 'ok' ? 'Run another' : 'Try again'}
        </button>
        {status === 'ok' && (
          <button
            onClick={onViewPerformance}
            className="text-sm text-blue-600 hover:underline"
          >
            View updated performance →
          </button>
        )}
        {status === 'ok' && onCalibrate && (
          <button
            onClick={onCalibrate}
            className="text-sm text-amber-600 hover:underline"
          >
            指标不理想？试试校准 →
          </button>
        )}
      </div>
    </div>
  );
}
