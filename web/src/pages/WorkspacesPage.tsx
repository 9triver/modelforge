import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { listWorkspaces, restartWorkspace, stopWorkspace } from '../lib/api';
import type { WorkspaceRecord } from '../lib/types';

const STATUS_STYLE: Record<string, { bg: string; dot: string; label: string }> = {
  creating: { bg: 'bg-blue-50 border-blue-200', dot: 'bg-blue-500 animate-pulse', label: 'Creating' },
  running: { bg: 'bg-green-50 border-green-200', dot: 'bg-green-500', label: 'Running' },
  stopping: { bg: 'bg-yellow-50 border-yellow-200', dot: 'bg-yellow-500 animate-pulse', label: 'Stopping' },
  stopped: { bg: 'bg-gray-50 border-gray-200', dot: 'bg-gray-400', label: 'Stopped' },
  error: { bg: 'bg-red-50 border-red-200', dot: 'bg-red-500', label: 'Error' },
};

function WorkspaceCard({
  ws,
  onRefresh,
}: {
  ws: WorkspaceRecord;
  onRefresh: () => void;
}) {
  const [acting, setActing] = useState(false);
  const style = STATUS_STYLE[ws.status] || STATUS_STYLE.error;

  const handleStop = async () => {
    setActing(true);
    try {
      await stopWorkspace(ws.id);
      onRefresh();
    } catch { /* ignore */ }
    setActing(false);
  };

  const handleRestart = async () => {
    setActing(true);
    try {
      await restartWorkspace(ws.id);
      onRefresh();
    } catch { /* ignore */ }
    setActing(false);
  };

  const repoLink = ws.repo ? `/${ws.repo}` : '#';

  return (
    <div className={'rounded-lg border p-4 ' + style.bg}>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className={'inline-block w-2.5 h-2.5 rounded-full ' + style.dot} />
          <Link to={repoLink} className="font-mono font-semibold text-gray-900 hover:text-blue-600 hover:underline">
            {ws.repo}
          </Link>
        </div>
        <span className="text-xs text-gray-500">{style.label}</span>
      </div>

      {(ws.models.length > 0 || ws.datasets.length > 0) && (
        <div className="mb-3 space-y-1">
          {ws.models.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              <span className="text-xs text-gray-500">Models:</span>
              {ws.models.map((m) => (
                <span key={m} className="text-xs px-2 py-0.5 bg-blue-100 text-blue-700 rounded">
                  {m}
                </span>
              ))}
            </div>
          )}
          {ws.datasets.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              <span className="text-xs text-gray-500">Datasets:</span>
              {ws.datasets.map((d) => (
                <span key={d} className="text-xs px-2 py-0.5 bg-purple-100 text-purple-700 rounded">
                  {d}
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="flex items-center justify-between">
        <span className="text-xs text-gray-400">
          Created {ws.created_at.slice(0, 10)}
        </span>
        <div className="flex gap-2">
          {ws.status === 'running' && (
            <>
              <a
                href={ws.url || '#'}
                target="_blank"
                rel="noopener noreferrer"
                className="px-3 py-1 text-xs bg-blue-600 text-white rounded hover:bg-blue-700"
              >
                Open IDE
              </a>
              <button
                onClick={handleStop}
                disabled={acting}
                className="px-3 py-1 text-xs border border-red-300 text-red-600 rounded hover:bg-red-50 disabled:opacity-50"
              >
                Stop
              </button>
            </>
          )}
          {ws.status === 'stopped' && (
            <button
              onClick={handleRestart}
              disabled={acting}
              className="px-3 py-1 text-xs bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
            >
              Restart
            </button>
          )}
          {ws.status === 'error' && ws.error && (
            <span className="text-xs text-red-600 max-w-xs truncate" title={ws.error}>
              {ws.error}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

export default function WorkspacesPage() {
  const [workspaces, setWorkspaces] = useState<WorkspaceRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const pollRef = useRef<number | null>(null);

  const refresh = () => {
    listWorkspaces().then(setWorkspaces).catch(() => {});
  };

  useEffect(() => {
    setLoading(true);
    listWorkspaces()
      .then(setWorkspaces)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    const hasActive = workspaces.some(
      (w) => w.status === 'creating' || w.status === 'stopping',
    );
    if (hasActive && !pollRef.current) {
      pollRef.current = window.setInterval(refresh, 2000);
    } else if (!hasActive && pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
      pollRef.current = null;
    };
  }, [workspaces]);

  return (
    <div className="max-w-4xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">Workspaces</h1>
        <p className="text-sm text-gray-500">
          Create workspaces from a Space repo page
        </p>
      </div>

      {loading && <div className="text-gray-500">Loading...</div>}

      {!loading && workspaces.length === 0 && (
        <div className="text-center py-16 text-gray-400">
          <div className="text-4xl mb-3">&#128187;</div>
          <div className="text-lg mb-1">No workspaces yet</div>
          <div className="text-sm">Create a Space repo and launch a workspace from its page</div>
        </div>
      )}

      <div className="space-y-3">
        {workspaces.map((ws) => (
          <WorkspaceCard key={ws.id} ws={ws} onRefresh={refresh} />
        ))}
      </div>
    </div>
  );
}
