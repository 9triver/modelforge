import { useEffect, useRef, useState } from 'react';
import {
  createWorkspace,
  getWorkspace,
  listWorkspaces,
  restartWorkspace,
  searchRepos,
  stopWorkspace,
} from '../lib/api';
import type { SearchResult, WorkspaceRecord } from '../lib/types';

const STATUS_COLOR: Record<string, string> = {
  creating: 'bg-blue-100 text-blue-700',
  running: 'bg-green-100 text-green-700',
  stopping: 'bg-yellow-100 text-yellow-700',
  stopped: 'bg-gray-100 text-gray-600',
  error: 'bg-red-100 text-red-700',
};

type Props = {
  namespace: string;
  name: string;
};

export default function WorkspaceTab({ namespace, name }: Props) {
  // --- config state ---
  const [wsName, setWsName] = useState(name + '-workspace');
  const [models, setModels] = useState<string[]>([namespace + '/' + name]);
  const [datasets, setDatasets] = useState<string[]>([]);
  const [searchType, setSearchType] = useState<'model' | 'dataset'>('dataset');
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [searching, setSearching] = useState(false);

  // --- workspace state ---
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [ws, setWs] = useState<WorkspaceRecord | null>(null);
  const [existing, setExisting] = useState<WorkspaceRecord[]>([]);
  const [stopping, setStopping] = useState(false);

  const pollRef = useRef<number | null>(null);

  // Load existing workspaces on mount
  useEffect(() => {
    listWorkspaces().then(setExisting).catch(() => {});
  }, []);

  // Cleanup polling
  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  const doSearch = async () => {
    setSearching(true);
    try {
      const results = await searchRepos({ repo_type: searchType });
      setSearchResults(
        results.filter(
          (r) =>
            !models.includes(r.full_name) &&
            !datasets.includes(r.full_name),
        ),
      );
    } catch {
      setSearchResults([]);
    }
    setSearching(false);
  };

  const addRepo = (fullName: string, type: 'model' | 'dataset') => {
    if (type === 'model' && !models.includes(fullName)) {
      setModels([...models, fullName]);
    } else if (type === 'dataset' && !datasets.includes(fullName)) {
      setDatasets([...datasets, fullName]);
    }
    setSearchResults([]);
  };

  const removeModel = (m: string) => setModels(models.filter((x) => x !== m));
  const removeDataset = (d: string) => setDatasets(datasets.filter((x) => x !== d));

  const pollWs = (id: number) => {
    pollRef.current = window.setInterval(async () => {
      try {
        const r = await getWorkspace(id);
        setWs(r);
        if (r.status === 'running' || r.status === 'error' || r.status === 'stopped') {
          if (pollRef.current) clearInterval(pollRef.current);
          pollRef.current = null;
        }
      } catch {
        /* retry */
      }
    }, 1500);
  };

  const handleCreate = async () => {
    setCreating(true);
    setCreateError(null);
    try {
      const { workspace_id } = await createWorkspace({
        namespace,
        name: wsName,
        models,
        datasets,
      });
      const r = await getWorkspace(workspace_id);
      setWs(r);
      pollWs(workspace_id);
    } catch (e: any) {
      setCreateError(e.message);
    }
    setCreating(false);
  };

  const handleStop = async () => {
    if (!ws) return;
    setStopping(true);
    try {
      await stopWorkspace(ws.id);
      setWs({ ...ws, status: 'stopping' });
      pollWs(ws.id);
    } catch {
      /* ignore */
    }
    setStopping(false);
  };

  const handleRestart = async () => {
    if (!ws) return;
    setCreating(true);
    try {
      await restartWorkspace(ws.id);
      setWs({ ...ws, status: 'creating' });
      pollWs(ws.id);
    } catch (e: any) {
      setCreateError(e.message);
    }
    setCreating(false);
  };

  const openWs = (rec: WorkspaceRecord) => {
    setWs(rec);
    if (rec.status === 'creating') pollWs(rec.id);
  };

  // --- Running state ---
  if (ws && ws.status === 'running') {
    return (
      <div className="space-y-4">
        <div className="flex items-center gap-3">
          <span className={'px-2 py-0.5 text-xs rounded ' + STATUS_COLOR.running}>
            Running
          </span>
          <span className="text-sm text-gray-500">{ws.repo}</span>
        </div>

        <div className="flex gap-3">
          <a
            href={ws.url || '#'}
            target="_blank"
            rel="noopener noreferrer"
            className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 text-sm"
          >
            Open in VS Code
          </a>
          <button
            onClick={handleStop}
            disabled={stopping}
            className="px-4 py-2 bg-red-50 text-red-700 border border-red-200 rounded hover:bg-red-100 text-sm disabled:opacity-50"
          >
            {stopping ? 'Stopping...' : 'Stop Workspace'}
          </button>
        </div>

        <div className="text-sm space-y-1">
          <div className="font-medium text-gray-700">Mounted Models:</div>
          {ws.models.map((m) => (
            <div key={m} className="text-gray-600 pl-2">
              {m}
            </div>
          ))}
          {ws.datasets.length > 0 && (
            <>
              <div className="font-medium text-gray-700 mt-2">Mounted Datasets:</div>
              {ws.datasets.map((d) => (
                <div key={d} className="text-gray-600 pl-2">
                  {d}
                </div>
              ))}
            </>
          )}
        </div>
      </div>
    );
  }

  // --- Creating / Stopping state ---
  if (ws && (ws.status === 'creating' || ws.status === 'stopping')) {
    return (
      <div className="space-y-4">
        <div className="flex items-center gap-3">
          <span className={'px-2 py-0.5 text-xs rounded ' + (STATUS_COLOR[ws.status] || '')}>
            {ws.status === 'creating' ? 'Creating...' : 'Stopping...'}
          </span>
        </div>
        <div className="flex items-center gap-2 text-sm text-gray-500">
          <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
            <circle
              className="opacity-25"
              cx="12" cy="12" r="10"
              stroke="currentColor"
              strokeWidth="4"
              fill="none"
            />
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
            />
          </svg>
          {ws.status === 'creating'
            ? 'Setting up workspace...'
            : 'Saving and stopping workspace...'}
        </div>
      </div>
    );
  }

  // --- Stopped state ---
  if (ws && ws.status === 'stopped') {
    return (
      <div className="space-y-4">
        <div className="flex items-center gap-3">
          <span className={'px-2 py-0.5 text-xs rounded ' + STATUS_COLOR.stopped}>
            Stopped
          </span>
          <span className="text-sm text-gray-500">{ws.repo}</span>
        </div>
        <button
          onClick={handleRestart}
          disabled={creating}
          className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 text-sm disabled:opacity-50"
        >
          {creating ? 'Restarting...' : 'Restart Workspace'}
        </button>
        {createError && (
          <div className="bg-red-50 text-red-700 p-3 rounded text-sm">{createError}</div>
        )}
      </div>
    );
  }

  // --- Error state ---
  if (ws && ws.status === 'error') {
    return (
      <div className="space-y-4">
        <div className="flex items-center gap-3">
          <span className={'px-2 py-0.5 text-xs rounded ' + STATUS_COLOR.error}>Error</span>
        </div>
        <div className="bg-red-50 text-red-700 p-3 rounded text-sm">
          {ws.error || 'Unknown error'}
        </div>
        <button
          onClick={() => setWs(null)}
          className="px-4 py-2 bg-gray-100 text-gray-700 border border-gray-200 rounded hover:bg-gray-200 text-sm"
        >
          Create New Workspace
        </button>
      </div>
    );
  }

  // --- Config state (default) ---
  return (
    <div className="space-y-6">
      {/* Existing workspaces */}
      {existing.length > 0 && (
        <div className="space-y-2">
          <div className="text-sm font-medium text-gray-700">Existing Workspaces</div>
          {existing.map((e) => (
            <div
              key={e.id}
              className="flex items-center justify-between p-2 border border-gray-200 rounded"
            >
              <div className="flex items-center gap-2">
                <span className={'px-2 py-0.5 text-xs rounded ' + (STATUS_COLOR[e.status] || '')}>
                  {e.status}
                </span>
                <span className="text-sm">{e.repo}</span>
              </div>
              <button
                onClick={() => openWs(e)}
                className="text-sm text-blue-600 hover:underline"
              >
                {e.status === 'running' ? 'Open' : 'View'}
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Create new workspace */}
      <div className="space-y-4">
        <div className="text-sm font-medium text-gray-700">Create New Workspace</div>

        <div>
          <label className="block text-sm text-gray-600 mb-1">Workspace Name</label>
          <input
            type="text"
            value={wsName}
            onChange={(e) => setWsName(e.target.value)}
            className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm"
            placeholder="my-workspace"
          />
        </div>

        {/* Selected models */}
        <div>
          <label className="block text-sm text-gray-600 mb-1">Models</label>
          <div className="flex flex-wrap gap-2">
            {models.map((m) => (
              <span
                key={m}
                className="inline-flex items-center gap-1 px-2 py-1 bg-blue-50 text-blue-700 rounded text-xs"
              >
                {m}
                <button
                  onClick={() => removeModel(m)}
                  className="text-blue-400 hover:text-blue-700"
                >
                  &times;
                </button>
              </span>
            ))}
          </div>
        </div>

        {/* Selected datasets */}
        <div>
          <label className="block text-sm text-gray-600 mb-1">Datasets</label>
          {datasets.length === 0 ? (
            <span className="text-xs text-gray-400">No datasets selected</span>
          ) : (
            <div className="flex flex-wrap gap-2">
              {datasets.map((d) => (
                <span
                  key={d}
                  className="inline-flex items-center gap-1 px-2 py-1 bg-green-50 text-green-700 rounded text-xs"
                >
                  {d}
                  <button
                    onClick={() => removeDataset(d)}
                    className="text-green-400 hover:text-green-700"
                  >
                    &times;
                  </button>
                </span>
              ))}
            </div>
          )}
        </div>

        {/* Search & add repos */}
        <div className="border border-gray-200 rounded p-3 space-y-2">
          <div className="flex gap-2 items-center">
            <select
              value={searchType}
              onChange={(e) => setSearchType(e.target.value as 'model' | 'dataset')}
              className="border border-gray-300 rounded px-2 py-1 text-sm"
            >
              <option value="model">Model</option>
              <option value="dataset">Dataset</option>
            </select>
            <button
              onClick={doSearch}
              disabled={searching}
              className="px-3 py-1 bg-gray-100 border border-gray-300 rounded text-sm hover:bg-gray-200 disabled:opacity-50"
            >
              {searching ? 'Loading...' : 'Browse'}
            </button>
          </div>
          {searchResults.length > 0 && (
            <div className="max-h-40 overflow-y-auto space-y-1">
              {searchResults.map((r) => (
                <div
                  key={r.full_name}
                  className="flex items-center justify-between p-1.5 hover:bg-gray-50 rounded text-sm cursor-pointer"
                  onClick={() => addRepo(r.full_name, searchType)}
                >
                  <span>{r.full_name}</span>
                  <span className="text-xs text-gray-400">
                    {r.pipeline_tag || r.data_format || ''}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Create button */}
        <button
          onClick={handleCreate}
          disabled={creating || !wsName}
          className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 text-sm disabled:bg-gray-300"
        >
          {creating ? 'Creating...' : 'Create Workspace'}
        </button>

        {createError && (
          <div className="bg-red-50 text-red-700 p-3 rounded text-sm">{createError}</div>
        )}
      </div>
    </div>
  );
}
