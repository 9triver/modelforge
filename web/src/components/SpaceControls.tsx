import { useEffect, useRef, useState } from 'react';
import {
  createWorkspace,
  getWorkspace,
  getWorkspaceByRepo,
  restartWorkspace,
  stopWorkspace,
} from '../lib/api';
import type { WorkspaceRecord } from '../lib/types';

const STATUS_COLOR: Record<string, string> = {
  creating: 'bg-blue-100 text-blue-700',
  running: 'bg-green-100 text-green-700',
  stopping: 'bg-yellow-100 text-yellow-700',
  stopped: 'bg-gray-100 text-gray-600',
  error: 'bg-red-100 text-red-700',
};

const STATUS_LABEL: Record<string, string> = {
  creating: 'Creating...',
  running: 'Running',
  stopping: 'Stopping...',
  stopped: 'Stopped',
  error: 'Error',
};

type Props = { namespace: string; name: string };

export default function SpaceControls({ namespace, name }: Props) {
  const [ws, setWs] = useState<WorkspaceRecord | null>(null);
  const [loading, setLoading] = useState(true);
  const [acting, setActing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<number | null>(null);

  const stopPoll = () => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  };

  const startPoll = (id: number) => {
    stopPoll();
    pollRef.current = window.setInterval(async () => {
      try {
        const r = await getWorkspace(id);
        setWs(r);
        if (r.status !== 'creating' && r.status !== 'stopping') stopPoll();
      } catch { /* retry */ }
    }, 1500);
  };

  useEffect(() => {
    setLoading(true);
    getWorkspaceByRepo(namespace, name)
      .then((list) => {
        if (list.length > 0) {
          setWs(list[0]);
          if (list[0].status === 'creating' || list[0].status === 'stopping') {
            startPoll(list[0].id);
          }
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false));
    return stopPoll;
  }, [namespace, name]);

  const handleLaunch = async () => {
    setActing(true);
    setError(null);
    try {
      const { workspace_id } = await createWorkspace({
        namespace,
        name,
        models: [],
        datasets: [],
      });
      const r = await getWorkspace(workspace_id);
      setWs(r);
      startPoll(workspace_id);
    } catch (e: any) {
      setError(e.message);
    }
    setActing(false);
  };

  const handleStop = async () => {
    if (!ws) return;
    setActing(true);
    try {
      await stopWorkspace(ws.id);
      setWs({ ...ws, status: 'stopping' });
      startPoll(ws.id);
    } catch { /* ignore */ }
    setActing(false);
  };

  const handleRestart = async () => {
    if (!ws) return;
    setActing(true);
    setError(null);
    try {
      await restartWorkspace(ws.id);
      setWs({ ...ws, status: 'creating' });
      startPoll(ws.id);
    } catch (e: any) {
      setError(e.message);
    }
    setActing(false);
  };

  if (loading) return <div className="text-gray-500 text-sm">Loading workspace status...</div>;

  // No workspace yet
  if (!ws) {
    return (
      <div className="space-y-4">
        <p className="text-sm text-gray-600">
          No workspace is associated with this space. Launch one to start an interactive development environment.
        </p>
        <button
          onClick={handleLaunch}
          disabled={acting}
          className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 text-sm disabled:bg-gray-300"
        >
          {acting ? 'Launching...' : 'Launch Workspace'}
        </button>
        {error && <div className="bg-red-50 text-red-700 p-3 rounded text-sm">{error}</div>}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <span className={'px-2 py-0.5 text-xs rounded font-medium ' + (STATUS_COLOR[ws.status] || '')}>
          {STATUS_LABEL[ws.status] || ws.status}
        </span>
        <span className="text-sm text-gray-500">{ws.repo}</span>
      </div>

      {(ws.status === 'creating' || ws.status === 'stopping') && (
        <div className="flex items-center gap-2 text-sm text-gray-500">
          <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          {ws.status === 'creating' ? 'Setting up workspace...' : 'Saving and stopping...'}
        </div>
      )}

      {ws.status === 'running' && (
        <div className="flex gap-3">
          <a
            href={ws.url || '#'}
            target="_blank"
            rel="noopener noreferrer"
            className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 text-sm"
          >
            Open IDE
          </a>
          <button
            onClick={handleStop}
            disabled={acting}
            className="px-4 py-2 bg-red-50 text-red-700 border border-red-200 rounded hover:bg-red-100 text-sm disabled:opacity-50"
          >
            Stop
          </button>
        </div>
      )}

      {ws.status === 'stopped' && (
        <button
          onClick={handleRestart}
          disabled={acting}
          className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 text-sm disabled:opacity-50"
        >
          {acting ? 'Restarting...' : 'Restart Workspace'}
        </button>
      )}

      {ws.status === 'error' && (
        <div className="space-y-3">
          <div className="bg-red-50 text-red-700 p-3 rounded text-sm">{ws.error || 'Unknown error'}</div>
          <button
            onClick={handleLaunch}
            disabled={acting}
            className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 text-sm disabled:bg-gray-300"
          >
            {acting ? 'Retrying...' : 'Retry'}
          </button>
        </div>
      )}

      {(ws.models.length > 0 || ws.datasets.length > 0) && (
        <div className="text-sm space-y-1 mt-2">
          {ws.models.length > 0 && (
            <>
              <div className="font-medium text-gray-700">Models (submodules):</div>
              {ws.models.map((m) => (
                <div key={m} className="text-gray-600 pl-2 font-mono text-xs">{m}</div>
              ))}
            </>
          )}
          {ws.datasets.length > 0 && (
            <>
              <div className="font-medium text-gray-700 mt-2">Datasets (submodules):</div>
              {ws.datasets.map((d) => (
                <div key={d} className="text-gray-600 pl-2 font-mono text-xs">{d}</div>
              ))}
            </>
          )}
        </div>
      )}

      {error && <div className="bg-red-50 text-red-700 p-3 rounded text-sm">{error}</div>}
    </div>
  );
}
