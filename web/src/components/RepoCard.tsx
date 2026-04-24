import { Link } from 'react-router-dom';
import type { SearchResult } from '../lib/types';

export default function RepoCard({ repo }: { repo: SearchResult }) {
  const isDataset = repo.repo_type === 'dataset';
  return (
    <Link
      to={`/${repo.namespace}/${repo.name}`}
      className={`block bg-white rounded-lg border p-4 hover:shadow-sm transition ${
        isDataset ? 'border-purple-200 hover:border-purple-400' : 'border-gray-200 hover:border-blue-400'
      }`}
    >
      <div className="flex items-center justify-between mb-2">
        <div className="font-mono text-base font-semibold text-gray-900">
          {repo.namespace}<span className="text-gray-400">/</span>{repo.name}
        </div>
        <div className="flex items-center gap-1.5">
          {isDataset && (
            <span className="text-xs px-2 py-0.5 bg-purple-50 text-purple-700 rounded font-medium">Dataset</span>
          )}
          {repo.license && (
            <span className="text-xs px-2 py-0.5 bg-gray-100 rounded text-gray-600">{repo.license}</span>
          )}
        </div>
      </div>
      <div className="flex flex-wrap gap-1.5 mb-2">
        {isDataset && repo.data_format && (
          <span className="text-xs px-2 py-0.5 bg-purple-50 text-purple-700 rounded">{repo.data_format}</span>
        )}
        {!isDataset && repo.library_name && (
          <span className="text-xs px-2 py-0.5 bg-blue-50 text-blue-700 rounded">{repo.library_name}</span>
        )}
        {repo.pipeline_tag && (
          <span className="text-xs px-2 py-0.5 bg-green-50 text-green-700 rounded">{repo.pipeline_tag}</span>
        )}
        {repo.tags.slice(0, 4).map((t) => (
          <span key={t} className="text-xs px-2 py-0.5 bg-gray-100 text-gray-600 rounded">{t}</span>
        ))}
        {repo.tags.length > 4 && (
          <span className="text-xs px-2 py-0.5 text-gray-400">+{repo.tags.length - 4}</span>
        )}
      </div>
      {repo.best_metric_name && repo.best_metric_value !== null && (
        <div className="text-xs text-gray-500">
          {repo.best_metric_name}: <span className="font-mono text-gray-800">{repo.best_metric_value}</span>
        </div>
      )}
      <div className="text-xs text-gray-400 mt-1">
        by {repo.owner}{repo.updated_at && ` · ${repo.updated_at.slice(0, 10)}`}
      </div>
    </Link>
  );
}
