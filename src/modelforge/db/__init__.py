"""SQLite 持久层。

拆分为子模块，但通过本文件重新导出所有公共 API，
保持 `from .. import db; db.get_repo(...)` 的调用方式不变。
"""
from .calibrations import create_calibration, get_calibration, update_calibration
from .connection import connect
from .evaluations import (
    aggregate_repo_metrics,
    create_evaluation,
    get_evaluation,
    update_evaluation,
)
from .models import (
    Calibration,
    Evaluation,
    Repo,
    RepoCard,
    Token,
    Transfer,
    User,
)
from .repo_cards import get_repo_card, search_repos, upsert_repo_card
from .repos import create_repo, delete_repo, get_repo, get_repo_name, list_repos
from .tokens import create_token, get_token, revoke_token
from .transfers import create_transfer, get_transfer, update_transfer
from .users import create_user, get_user_by_id, get_user_by_name, list_users

__all__ = [
    # models
    "User", "Token", "Repo", "RepoCard", "Evaluation", "Calibration", "Transfer",
    # connection
    "connect",
    # users
    "create_user", "get_user_by_name", "get_user_by_id", "list_users",
    # tokens
    "create_token", "get_token", "revoke_token",
    # repos
    "create_repo", "get_repo", "get_repo_name", "list_repos", "delete_repo",
    # repo_cards
    "upsert_repo_card", "get_repo_card", "search_repos",
    # evaluations
    "create_evaluation", "update_evaluation", "get_evaluation", "aggregate_repo_metrics",
    # calibrations
    "create_calibration", "update_calibration", "get_calibration",
    # transfers
    "create_transfer", "update_transfer", "get_transfer",
]
