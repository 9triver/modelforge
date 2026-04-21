export interface RepoSummary {
  namespace: string;
  name: string;
  full_name: string;
  owner: string;
  is_private: boolean;
  created_at: string;
  git_url: string;
}

export interface SearchResult {
  namespace: string;
  name: string;
  full_name: string;
  owner: string;
  library_name: string | null;
  pipeline_tag: string | null;
  license: string | null;
  tags: string[];
  base_model: string | null;
  best_metric_name: string | null;
  best_metric_value: number | null;
  revision: string | null;
  updated_at: string | null;
}

export interface FileItem {
  path: string;
  size: number;
  size_human: string;
  is_lfs: boolean;
}

export interface ModelIndexRow {
  task: string;
  dataset: string;
  metric: string;
  value: number | string;
}

export interface Preview {
  namespace: string;
  name: string;
  full_name: string;
  owner: string;
  revision: string;
  has_commits: boolean;
  metadata: Record<string, any> | null;
  body_html: string | null;
  body_error: string | null;
  model_index: ModelIndexRow[];
  files: FileItem[];
  refs: { branches: string[]; tags: string[] };
}

export interface Facets {
  libraries: string[];
  tasks: string[];
  licenses: string[];
  tags: string[];
}
