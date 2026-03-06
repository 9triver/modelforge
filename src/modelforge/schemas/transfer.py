from pydantic import BaseModel, Field


class ExportRequest(BaseModel):
    version_ids: list[str] | None = None  # None = all versions
    include_runs: bool = False
    include_datasets: bool = True


class ExportManifest(BaseModel):
    format_version: str = "1.0"
    exported_at: str
    source_model_id: str
    source_model_name: str
    versions_included: list[str]


class ImportPreviewResponse(BaseModel):
    model_name: str
    source_model_id: str
    algorithm_type: str | None = None
    framework: str | None = None
    versions: list[dict]
    has_pipeline: bool
    name_collision: bool
    suggested_name: str
