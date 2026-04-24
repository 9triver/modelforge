import type {
  AggregateMetrics,
  CalibrationRecord,
  CsvPreview,
  Evaluation,
  Facets,
  ImagePreview,
  Preview,
  RepoSummary,
  SearchResult,
  TransferRecord,
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
  repo_type?: string;
  data_format?: string;
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
  dataset: File | null,
  revision = 'main',
  datasetRepo?: string,
): Promise<{ evaluation_id: number; status: string }> {
  const qs = new URLSearchParams({ revision });
  if (datasetRepo) qs.set('dataset_repo', datasetRepo);
  const fd = new FormData();
  if (dataset) fd.append('dataset', dataset);
  const res = await fetch(
    `/api/v1/repos/${namespace}/${name}/evaluate?${qs}`,
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
  dataset: File | null,
  revision = 'main',
  method = 'linear_bias',
  datasetRepo?: string,
): Promise<{ calibration_id: number; status: string }> {
  const qs = new URLSearchParams({ revision, method });
  if (datasetRepo) qs.set('dataset_repo', datasetRepo);
  const fd = new FormData();
  if (dataset) fd.append('dataset', dataset);
  const res = await fetch(
    `/api/v1/repos/${namespace}/${name}/calibrate/preview?${qs}`,
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

export async function postTransferPreview(
  namespace: string,
  name: string,
  dataset: File | null,
  revision = 'main',
  method = 'linear_probe',
  hparams: { epochs?: number; lr?: number; unfreeze_layers?: number } = {},
  datasetRepo?: string,
): Promise<{ transfer_id: number; status: string }> {
  const fd = new FormData();
  if (dataset) fd.append('dataset', dataset);
  const qs = new URLSearchParams({
    revision,
    method,
    ...(hparams.epochs != null ? { epochs: String(hparams.epochs) } : {}),
    ...(hparams.lr != null ? { lr: String(hparams.lr) } : {}),
    ...(hparams.unfreeze_layers != null ? { unfreeze_layers: String(hparams.unfreeze_layers) } : {}),
  });
  if (datasetRepo) qs.set('dataset_repo', datasetRepo);
  const res = await fetch(
    `/api/v1/repos/${namespace}/${name}/transfer/preview?${qs}`,
    { method: 'POST', body: fd },
  );
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${body}`);
  }
  return res.json();
}

export async function saveTransfer(
  transferId: number,
  targetNamespace: string,
  targetName: string,
): Promise<{ target_repo: string; target_revision: string }> {
  const res = await fetch(`/api/v1/transfers/${transferId}/save`, {
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

export function getTransfer(id: number): Promise<TransferRecord> {
  return getJSON(`/api/v1/transfers/${id}`);
}

export async function deleteRepo(
  namespace: string,
  name: string,
): Promise<void> {
  const res = await fetch(`/api/v1/repos/${namespace}/${name}/force`, {
    method: 'DELETE',
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${body}`);
  }
}

export function getCsvPreview(
  namespace: string,
  name: string,
  path: string,
  revision = 'main',
  limit = 100,
): Promise<CsvPreview> {
  const qs = new URLSearchParams({ path, revision, limit: String(limit) });
  return getJSON(`/api/v1/repos/${namespace}/${name}/preview-csv?${qs}`);
}

export function getImagePreview(
  namespace: string,
  name: string,
  revision = 'main',
  limit = 20,
): Promise<ImagePreview> {
  const qs = new URLSearchParams({ revision, limit: String(limit) });
  return getJSON(`/api/v1/repos/${namespace}/${name}/preview-images?${qs}`);
}

export function listDatasetRepos(dataFormat?: string): Promise<SearchResult[]> {
  return searchRepos({ repo_type: 'dataset', data_format: dataFormat });
}
