import { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { getPreview, getRepoMetrics, deleteRepo } from '../lib/api';
import type { AggregateMetrics, Preview } from '../lib/types';
import CalibrateTab from '../components/CalibrateTab';
import EvaluateTab from '../components/EvaluateTab';
import FileList from '../components/FileList';
import ModelIndexTable from '../components/ModelIndexTable';
import PerformanceBadge from '../components/PerformanceBadge';
import UseModelSnippet from '../components/UseModelSnippet';

type Tab = 'card' | 'files' | 'evaluate' | 'calibrate';

export default function RepoPage() {
  const { namespace = '', name = '' } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const tabParam = searchParams.get('tab');
  const tab: Tab =
    tabParam === 'files' ? 'files' : tabParam === 'evaluate' ? 'evaluate' : tabParam === 'calibrate' ? 'calibrate' : 'card';
  const revision = searchParams.get('revision') || 'main';

  const [preview, setPreview] = useState<Preview | null>(null);
  const [agg, setAgg] = useState<AggregateMetrics | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [showDelete, setShowDelete] = useState(false);
  const [deleteToken, setDeleteToken] = useState('');
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const navigate = useNavigate();

  const loadAgg = useCallback(() => {
    getRepoMetrics(namespace, name).then(setAgg).catch(() => setAgg(null));
  }, [namespace, name]);

  useEffect(() => {
    setLoading(true);
    setError(null);
    getPreview(namespace, name, revision)
      .then(setPreview)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [namespace, name, revision]);

  useEffect(() => {
    loadAgg();
  }, [loadAgg]);

  if (loading) return <div className="text-gray-500">加载中...</div>;
  if (error) return <div className="bg-red-50 text-red-700 p-4 rounded">{error}</div>;
  if (!preview) return null;

  const meta = preview.metadata || {};
  const gitUrl = `${window.location.protocol}//${window.location.host}/${preview.full_name}.git`;
  const setTab = (t: Tab) => setSearchParams({ tab: t, revision });

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-6">
      <div className="min-w-0">
        <div className="mb-4">
          <Link to="/" className="text-sm text-blue-600 hover:underline">← 返回列表</Link>
          <h1 className="text-2xl font-bold mt-2 font-mono">
            {preview.namespace}<span className="text-gray-400">/</span>{preview.name}
          </h1>
          <div className="text-sm text-gray-500 mt-1">
            by {preview.owner} · revision: <code className="bg-gray-100 px-1 rounded">{preview.revision}</code>
          </div>
        </div>

        <div className="border-b border-gray-200 mb-4 flex gap-1">
          {(['card', 'files', 'evaluate', 'calibrate'] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px ${
                tab === t
                  ? 'border-blue-600 text-blue-600'
                  : 'border-transparent text-gray-600 hover:text-gray-900'
              }`}
            >
              {t === 'card'
                ? 'Model Card'
                : t === 'files'
                ? `Files (${preview.files.length})`
                : t === 'evaluate'
                ? 'Evaluate'
                : 'Calibrate'}
            </button>
          ))}
        </div>

        {tab === 'card' && (
          <div>
            {agg && <PerformanceBadge agg={agg} />}
            <UseModelSnippet fullName={preview.full_name} task={meta.pipeline_tag || null} />
            {preview.body_error && (
              <div className="bg-yellow-50 text-yellow-800 p-3 rounded mb-4 whitespace-pre-wrap text-sm">
                {preview.body_error}
              </div>
            )}
            {preview.model_index.length > 0 && (
              <>
                <h2 className="text-lg font-semibold mt-2 mb-2">Reported metrics (model_card)</h2>
                <ModelIndexTable rows={preview.model_index} />
              </>
            )}
            {preview.body_html && (
              <div
                className="prose-body max-w-none"
                dangerouslySetInnerHTML={{ __html: preview.body_html }}
              />
            )}
          </div>
        )}

        {tab === 'files' && (
          <FileList
            files={preview.files}
            namespace={namespace}
            name={name}
            revision={revision}
          />
        )}

        {tab === 'evaluate' && (
          <EvaluateTab
            namespace={namespace}
            name={name}
            revision={revision}
            task={meta.pipeline_tag || null}
            onDone={() => {
              loadAgg();
              setTab('card');
            }}
            onCalibrate={() => setTab('calibrate')}
          />
        )}

        {tab === 'calibrate' && (
          <CalibrateTab
            namespace={namespace}
            name={name}
            revision={revision}
            task={meta.pipeline_tag || null}
          />
        )}
      </div>

      <aside className="space-y-4 text-sm">
        <div className="bg-white border border-gray-200 rounded p-4">
          <div className="text-xs font-semibold text-gray-500 uppercase mb-2">Clone</div>
          <code className="block text-xs bg-gray-50 p-2 rounded break-all">git clone {gitUrl}</code>
        </div>

        {(meta.license || meta.library_name || meta.pipeline_tag) && (
          <div className="bg-white border border-gray-200 rounded p-4 space-y-2">
            {meta.library_name && <div><span className="text-gray-500">Library:</span> <span className="font-medium">{meta.library_name}</span></div>}
            {meta.pipeline_tag && <div><span className="text-gray-500">Task:</span> <span className="font-medium">{meta.pipeline_tag}</span></div>}
            {meta.license && <div><span className="text-gray-500">License:</span> <span className="font-medium">{meta.license}</span></div>}
            {meta.base_model && <div><span className="text-gray-500">Base:</span> <span className="font-mono text-xs">{meta.base_model}</span></div>}
          </div>
        )}

        {Array.isArray(meta.tags) && meta.tags.length > 0 && (
          <div className="bg-white border border-gray-200 rounded p-4">
            <div className="text-xs font-semibold text-gray-500 uppercase mb-2">Tags</div>
            <div className="flex flex-wrap gap-1">
              {meta.tags.map((t: string) => (
                <span key={t} className="text-xs px-2 py-0.5 bg-gray-100 text-gray-700 rounded">{t}</span>
              ))}
            </div>
          </div>
        )}

        {(preview.refs.branches.length > 0 || preview.refs.tags.length > 0) && (
          <div className="bg-white border border-gray-200 rounded p-4">
            <div className="text-xs font-semibold text-gray-500 uppercase mb-2">Refs</div>
            <div className="space-y-1 text-xs">
              {preview.refs.branches.map((b) => (
                <button
                  key={b}
                  onClick={() => setSearchParams({ tab, revision: b })}
                  className={`block font-mono ${revision === b ? 'text-blue-600 font-semibold' : 'text-gray-600 hover:text-gray-900'}`}
                >
                  🌿 {b}
                </button>
              ))}
              {preview.refs.tags.map((t) => (
                <button
                  key={t}
                  onClick={() => setSearchParams({ tab, revision: t })}
                  className={`block font-mono ${revision === t ? 'text-blue-600 font-semibold' : 'text-gray-600 hover:text-gray-900'}`}
                >
                  🏷 {t}
                </button>
              ))}
            </div>
          </div>
        )}

        <div className="bg-white border border-red-200 rounded p-4">
          {!showDelete ? (
            <button
              onClick={() => setShowDelete(true)}
              className="text-xs text-red-500 hover:text-red-700"
            >
              Delete this repository
            </button>
          ) : (
            <div className="space-y-2">
              <div className="text-xs text-red-700 font-semibold">
                确认删除 {preview.full_name}？此操作不可撤销。
              </div>
              <input
                type="password"
                value={deleteToken}
                onChange={(e) => setDeleteToken(e.target.value)}
                placeholder="输入 Token 确认"
                className="w-full border border-gray-300 rounded px-2 py-1 text-xs"
              />
              {deleteError && (
                <div className="text-xs text-red-600">{deleteError}</div>
              )}
              <div className="flex gap-2">
                <button
                  disabled={!deleteToken || deleting}
                  onClick={async () => {
                    setDeleting(true);
                    setDeleteError(null);
                    try {
                      await deleteRepo(namespace, name, deleteToken);
                      navigate('/');
                    } catch (e: any) {
                      setDeleteError(e.message || String(e));
                    } finally {
                      setDeleting(false);
                    }
                  }}
                  className="px-3 py-1 text-xs rounded bg-red-600 text-white disabled:bg-gray-300"
                >
                  {deleting ? '删除中…' : '确认删除'}
                </button>
                <button
                  onClick={() => { setShowDelete(false); setDeleteToken(''); setDeleteError(null); }}
                  className="px-3 py-1 text-xs rounded border border-gray-300 hover:bg-gray-50"
                >
                  取消
                </button>
              </div>
            </div>
          )}
        </div>
      </aside>
    </div>
  );
}
