from __future__ import annotations

from .connection import connect
from .models import Repo, RepoCard
from .repos import _row_to_repo


def upsert_repo_card(card: RepoCard) -> None:
    with connect() as c:
        c.execute(
            """
            INSERT INTO repo_cards
                (repo_id, revision, library_name, pipeline_tag, license,
                 tags_json, base_model, best_metric_name, best_metric_value,
                 updated_at, repo_type, data_format)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(repo_id) DO UPDATE SET
                revision = excluded.revision,
                library_name = excluded.library_name,
                pipeline_tag = excluded.pipeline_tag,
                license = excluded.license,
                tags_json = excluded.tags_json,
                base_model = excluded.base_model,
                best_metric_name = excluded.best_metric_name,
                best_metric_value = excluded.best_metric_value,
                updated_at = excluded.updated_at,
                repo_type = excluded.repo_type,
                data_format = excluded.data_format
            """,
            (
                card.repo_id, card.revision, card.library_name, card.pipeline_tag,
                card.license, card.tags_json, card.base_model,
                card.best_metric_name, card.best_metric_value, card.updated_at,
                card.repo_type, card.data_format,
            ),
        )


def get_repo_card(repo_id: int) -> RepoCard | None:
    with connect() as c:
        row = c.execute("SELECT * FROM repo_cards WHERE repo_id = ?", (repo_id,)).fetchone()
        return RepoCard(**dict(row)) if row else None


def search_repos(
    library_name: str | None = None,
    pipeline_tag: str | None = None,
    license_: str | None = None,
    tag: str | None = None,
    max_metric: float | None = None,
    metric_name: str | None = None,
    repo_type: str | None = None,
    data_format: str | None = None,
    limit: int = 100,
) -> list[tuple[Repo, RepoCard | None]]:
    """组合条件搜索仓库。返回 (repo, card) 列表。"""
    sql = """
        SELECT r.*, c.repo_id AS c_repo_id, c.revision, c.library_name, c.pipeline_tag,
               c.license, c.tags_json, c.base_model,
               c.best_metric_name, c.best_metric_value, c.updated_at,
               c.repo_type, c.data_format
        FROM repos r
        LEFT JOIN repo_cards c ON r.id = c.repo_id
        WHERE 1=1
    """
    args: list = []
    if library_name:
        sql += " AND c.library_name = ?"
        args.append(library_name)
    if pipeline_tag:
        sql += " AND c.pipeline_tag = ?"
        args.append(pipeline_tag)
    if license_:
        sql += " AND c.license = ?"
        args.append(license_)
    if tag:
        sql += " AND c.tags_json LIKE ?"
        args.append(f'%"{tag}"%')
    if max_metric is not None:
        sql += " AND c.best_metric_value IS NOT NULL AND c.best_metric_value <= ?"
        args.append(max_metric)
    if metric_name:
        sql += " AND c.best_metric_name = ?"
        args.append(metric_name)
    if repo_type:
        sql += " AND COALESCE(c.repo_type, 'model') = ?"
        args.append(repo_type)
    if data_format:
        sql += " AND c.data_format = ?"
        args.append(data_format)
    sql += " ORDER BY r.namespace, r.name LIMIT ?"
    args.append(limit)

    with connect() as c:
        rows = c.execute(sql, tuple(args)).fetchall()

    out: list[tuple[Repo, RepoCard | None]] = []
    for r in rows:
        repo = _row_to_repo(r)
        card = None
        if r["c_repo_id"] is not None:
            card = RepoCard(
                repo_id=r["c_repo_id"], revision=r["revision"],
                library_name=r["library_name"], pipeline_tag=r["pipeline_tag"],
                license=r["license"], tags_json=r["tags_json"],
                base_model=r["base_model"],
                best_metric_name=r["best_metric_name"],
                best_metric_value=r["best_metric_value"],
                updated_at=r["updated_at"],
                repo_type=r["repo_type"] or "model",
                data_format=r["data_format"],
            )
        out.append((repo, card))
    return out
