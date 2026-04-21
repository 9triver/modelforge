import type { ModelIndexRow } from '../lib/types';

export default function ModelIndexTable({ rows }: { rows: ModelIndexRow[] }) {
  if (rows.length === 0) return null;
  return (
    <div className="overflow-x-auto my-4">
      <table className="w-full border border-gray-200 text-sm">
        <thead className="bg-gray-50">
          <tr>
            <th className="border border-gray-200 px-3 py-2 text-left">Task</th>
            <th className="border border-gray-200 px-3 py-2 text-left">Dataset</th>
            <th className="border border-gray-200 px-3 py-2 text-left">Metric</th>
            <th className="border border-gray-200 px-3 py-2 text-right">Value</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="even:bg-gray-50">
              <td className="border border-gray-200 px-3 py-2">{r.task}</td>
              <td className="border border-gray-200 px-3 py-2">{r.dataset}</td>
              <td className="border border-gray-200 px-3 py-2">{r.metric}</td>
              <td className="border border-gray-200 px-3 py-2 text-right font-mono">{r.value}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
