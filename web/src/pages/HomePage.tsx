import { useEffect, useMemo, useState } from 'react';
import { getFacets, listRepos, searchRepos } from '../lib/api';
import type { Facets, SearchResult } from '../lib/types';
import FacetFilter from '../components/FacetFilter';
import RepoCard from '../components/RepoCard';

export default function HomePage() {
  const [facets, setFacets] = useState<Facets>({ libraries: [], tasks: [], licenses: [], tags: [], repo_types: [], data_formats: [] });
  const [library, setLibrary] = useState('');
  const [task, setTask] = useState('');
  const [tag, setTag] = useState('');
  const [maxMape, setMaxMape] = useState('');
  const [repoType, setRepoType] = useState('');
  const [dataFormat, setDataFormat] = useState('');
  const [query, setQuery] = useState('');
  const [repos, setRepos] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getFacets().then(setFacets).catch((e) => console.warn('facets', e));
  }, []);

  const hasFilter = library || task || tag || maxMape || repoType || dataFormat;

  useEffect(() => {
    setLoading(true);
    setError(null);
    const promise = hasFilter
      ? searchRepos({
          library: library || undefined,
          pipeline_tag: task || undefined,
          tag: tag || undefined,
          max_metric: maxMape ? parseFloat(maxMape) : undefined,
          metric: maxMape ? 'mape' : undefined,
          repo_type: repoType || undefined,
          data_format: dataFormat || undefined,
        })
      : listRepos().then((rows) =>
          rows.map((r) => ({
            namespace: r.namespace,
            name: r.name,
            full_name: r.full_name,
            owner: r.owner,
            library_name: null,
            pipeline_tag: null,
            license: null,
            tags: [],
            base_model: null,
            best_metric_name: null,
            best_metric_value: null,
            revision: null,
            updated_at: r.created_at,
            repo_type: 'model',
            data_format: null,
          }))
        );
    promise
      .then(setRepos)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [library, task, tag, maxMape, repoType, dataFormat, hasFilter]);

  const filtered = useMemo(() => {
    if (!query) return repos;
    const q = query.toLowerCase();
    return repos.filter(
      (r) =>
        r.full_name.toLowerCase().includes(q) ||
        r.tags.some((t) => t.toLowerCase().includes(q)),
    );
  }, [repos, query]);

  return (
    <div className="flex gap-6">
      <FacetFilter
        facets={facets}
        library={library}
        task={task}
        tag={tag}
        maxMape={maxMape}
        repoType={repoType}
        dataFormat={dataFormat}
        onChange={(u) => {
          if (u.library !== undefined) setLibrary(u.library);
          if (u.task !== undefined) setTask(u.task);
          if (u.tag !== undefined) setTag(u.tag);
          if (u.maxMape !== undefined) setMaxMape(u.maxMape);
          if (u.repoType !== undefined) setRepoType(u.repoType);
          if (u.dataFormat !== undefined) setDataFormat(u.dataFormat);
        }}
      />
      <div className="flex-1 min-w-0">
        <div className="mb-4 flex items-center gap-3">
          <input
            type="text"
            placeholder="搜索仓库名或标签..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="flex-1 border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:border-blue-500"
          />
          <div className="text-sm text-gray-500 whitespace-nowrap">
            {loading ? '加载中...' : `${filtered.length} 个仓库`}
          </div>
        </div>
        {error && <div className="bg-red-50 text-red-700 p-3 rounded mb-4">{error}</div>}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {filtered.map((r) => (
            <RepoCard key={r.full_name} repo={r} />
          ))}
        </div>
        {!loading && filtered.length === 0 && (
          <div className="text-center py-10 text-gray-500">没有匹配的仓库</div>
        )}
      </div>
    </div>
  );
}
