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

export interface AggregateMetrics {
  count: number;
  metric: string | null;
  median: number | null;
  p25: number | null;
  p75: number | null;
}

export interface Evaluation {
  id: number;
  repo: string;
  revision: string;
  task: string;
  status: 'queued' | 'running' | 'ok' | 'error';
  metrics: Record<string, number | null> | null;
  primary_metric: string | null;
  primary_value: number | null;
  duration_ms: number | null;
  error: string | null;
  created_at: string;
}

export interface CalibrationRecord {
  id: number;
  source_repo: string;
  source_revision: string;
  target_repo: string | null;
  target_revision: string | null;
  method: string;
  params: Record<string, number> | null;
  before_metrics: Record<string, number | null> | null;
  after_metrics: Record<string, number | null> | null;
  primary_metric: string | null;
  before_value: number | null;
  after_value: number | null;
  status: 'queued' | 'running' | 'previewed' | 'saving' | 'ok' | 'error';
  duration_ms: number | null;
  error: string | null;
  created_at: string;
}

export interface TransferRecord {
  id: number;
  source_repo: string;
  source_revision: string;
  target_repo: string | null;
  target_revision: string | null;
  method: string;
  classes: string[] | null;
  n_classes: number | null;
  n_samples: number | null;
  after_metrics: Record<string, number | null> | null;
  primary_metric: string | null;
  after_value: number | null;
  hparams: Record<string, number | string> | null;
  current_epoch: number | null;
  total_epochs: number | null;
  status: 'queued' | 'running' | 'previewed' | 'saving' | 'ok' | 'error';
  duration_ms: number | null;
  error: string | null;
  created_at: string;
}
