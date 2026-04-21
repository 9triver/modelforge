import type { AggregateMetrics } from '../lib/types';

function fmt(v: number | null): string {
  if (v == null) return '—';
  if (Math.abs(v) >= 100) return v.toFixed(2);
  if (Math.abs(v) >= 1) return v.toFixed(3);
  return v.toFixed(4);
}

export default function PerformanceBadge({ agg }: { agg: AggregateMetrics }) {
  if (agg.count === 0 || !agg.metric) return null;

  return (
    <div className="bg-blue-50 border border-blue-200 rounded p-3 mb-4 text-sm flex items-center gap-4 flex-wrap">
      <div className="font-semibold text-blue-900">
        Performance ({agg.count} {agg.count === 1 ? 'evaluation' : 'evaluations'})
      </div>
      <div className="flex gap-4 text-gray-700">
        <span>
          <span className="text-gray-500">{agg.metric.toUpperCase()}</span>{' '}
          <span className="font-mono font-medium">median {fmt(agg.median)}</span>
        </span>
        <span className="text-gray-400">·</span>
        <span className="font-mono text-gray-600">
          p25 {fmt(agg.p25)} / p75 {fmt(agg.p75)}
        </span>
      </div>
    </div>
  );
}
