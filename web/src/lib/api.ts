import type { Facets, Preview, RepoSummary, SearchResult } from './types';

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
