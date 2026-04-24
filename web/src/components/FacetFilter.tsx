import type { Facets } from '../lib/types';

interface Props {
  facets: Facets;
  library: string;
  task: string;
  tag: string;
  maxMape: string;
  repoType: string;
  dataFormat: string;
  onChange: (update: Partial<{ library: string; task: string; tag: string; maxMape: string; repoType: string; dataFormat: string }>) => void;
}

function Section({ title, options, value, onChange }: {
  title: string;
  options: string[];
  value: string;
  onChange: (v: string) => void;
}) {
  if (options.length === 0) return null;
  return (
    <div className="mb-4">
      <div className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">{title}</div>
      <div className="space-y-1">
        <button
          onClick={() => onChange('')}
          className={`block w-full text-left text-sm px-2 py-1 rounded ${
            value === '' ? 'bg-blue-100 text-blue-800 font-medium' : 'text-gray-600 hover:bg-gray-100'
          }`}
        >
          全部
        </button>
        {options.map((o) => (
          <button
            key={o}
            onClick={() => onChange(o)}
            className={`block w-full text-left text-sm px-2 py-1 rounded truncate ${
              value === o ? 'bg-blue-100 text-blue-800 font-medium' : 'text-gray-600 hover:bg-gray-100'
            }`}
          >
            {o}
          </button>
        ))}
      </div>
    </div>
  );
}

export default function FacetFilter({ facets, library, task, tag, maxMape, repoType, dataFormat, onChange }: Props) {
  const isDataset = repoType === 'dataset';
  return (
    <aside className="w-56 shrink-0">
      <div className="sticky top-4">
        <Section title="Type" options={['model', 'dataset']} value={repoType} onChange={(v) => onChange({ repoType: v })} />
        {!isDataset && (
          <Section title="Library" options={facets.libraries} value={library} onChange={(v) => onChange({ library: v })} />
        )}
        {isDataset && facets.data_formats.length > 0 && (
          <Section title="Data Format" options={facets.data_formats} value={dataFormat} onChange={(v) => onChange({ dataFormat: v })} />
        )}
        <Section title="Task" options={facets.tasks} value={task} onChange={(v) => onChange({ task: v })} />
        <Section title="Tags" options={facets.tags} value={tag} onChange={(v) => onChange({ tag: v })} />
        {!isDataset && (
          <div className="mb-4">
            <div className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Max MAPE</div>
            <input
              type="number"
              step="0.1"
              placeholder="不限"
              value={maxMape}
              onChange={(e) => onChange({ maxMape: e.target.value })}
              className="w-full text-sm border border-gray-300 rounded px-2 py-1"
            />
          </div>
        )}
      </div>
    </aside>
  );
}
