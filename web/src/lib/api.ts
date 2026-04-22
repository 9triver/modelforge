import type {
  AggregateMetrics,
  CalibrationRecord,
  Evaluation,
  Facets,
  Preview,
  RepoSummary,
  SearchResult,
} from './types';

async function getJSON<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}: ${url}`);
  return res.json();
}

export function listRepos(): Promise<RepoSummary[]> {
  return getJSON('/api/v1/repos');
}

export function searchRepos(params: {
  library?: string;
  pipeline_tag?: string;
  license?: string;
  tag?: string;
  max_metric?: number;
  metric?: string;
}): Promise<SearchResult[]> {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== '') qs.set(k, String(v));
  });
  return getJSON(`/api/v1/repos/search?${qs}`);
}

export function getFacets(): Promise<Facets> {
  return getJSON('/api/v1/facets');
}

export function getPreview(namespace: string, name: string, revision = 'main'): Promise<Preview> {
  return getJSON(`/api/v1/repos/${namespace}/${name}/preview?revision=${encodeURIComponent(revision)}`);
}

export function getRepoMetrics(namespace: string, name: string): Promise<AggregateMetrics> {
  return getJSON(`/api/v1/repos/${namespace}/${name}/metrics`);
}

export async function postEvaluation(
  namespace: string,
  name: string,
  dataset: File,
  revision = 'main',
): Promise<{ evaluation_id: number; status: string }> {
  const fd = new FormData();
  fd.append('dataset', dataset);
  const res = await fetch(
    `/api/v1/repos/${namespace}/${name}/evaluate?revision=${encodeURIComponent(revision)}`,
    { method: 'POST', body: fd },
  );
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${body}`);
  }
  return res.json();
}

export function getEvaluation(id: number): Promise<Evaluation> {
  return getJSON(`/api/v1/evaluations/${id}`);
}

export async function postCalibrationPreview(
  namespace: string,
  name: string,
  dataset: File,
  revision = 'main',
): Promise<{ calibration_id: number; status: string }> {
  const fd = new FormData();
  fd.append('dataset', dataset);
  const res = await fetch(
    `/api/v1/repos/${namespace}/${name}/calibrate/preview?revision=${encodeURIComponent(revision)}`,
    { method: 'POST', body: fd },
  );
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${body}`);
  }
  return res.json();
}

export async function saveCalibration(
  calId: number,
  targetNamespace: string,
  targetName: string,
): Promise<{ target_repo: string; target_revision: string }> {
  const res = await fetch(`/api/v1/calibrations/${calId}/save`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ target_namespace: targetNamespace, target_name: targetName }),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${body}`);
  }
  return res.json();
}

export function getCalibration(id: number): Promise<CalibrationRecord> {
  return getJSON(`/api/v1/calibrations/${id}`);
}

export async function deleteRepo(
  namespace: string,
  name: string,
  token: string,
): Promise<void> {
  const res = await fetch(`/api/v1/repos/${namespace}/${name}`, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${body}`);
  }
}
