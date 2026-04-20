"""ModelForge CLI."""
from __future__ import annotations

import typer
import uvicorn
from rich.console import Console
from rich.table import Table

from . import db
from .auth import generate_token
from .config import get_settings

app = typer.Typer(help="ModelForge — Git+LFS Model Hub", no_args_is_help=True)
console = Console()

user_app = typer.Typer(help="用户管理")
token_app = typer.Typer(help="Token 管理")
repo_app = typer.Typer(help="仓库管理（直接读 SQLite，不走 HTTP API）")
app.add_typer(user_app, name="user")
app.add_typer(token_app, name="token")
app.add_typer(repo_app, name="repo")


# ---------- serve ----------

@app.command()
def serve(
    host: str = typer.Option(None, help="覆盖配置中的 host"),
    port: int = typer.Option(None, help="覆盖配置中的 port"),
    data: str = typer.Option(None, help="覆盖数据目录"),
    reload: bool = typer.Option(False, help="开发模式自动重载"),
):
    """启动 ModelForge 服务。"""
    if data:
        from .config import reset_settings
        reset_settings(data_dir=data)
    settings = get_settings()
    console.print(f"[green]启动 ModelForge[/green] data={settings.data_dir}")
    console.print(f"[cyan]API 文档:[/cyan] http://{host or settings.host}:{port or settings.port}/docs")
    uvicorn.run(
        "modelforge.server:app",
        host=host or settings.host,
        port=port or settings.port,
        reload=reload,
    )


# ---------- user ----------

@user_app.command("create")
def user_create(name: str):
    """创建用户并签发首个 Token。"""
    if db.get_user_by_name(name):
        console.print(f"[red]用户 '{name}' 已存在[/red]")
        raise typer.Exit(1)
    user = db.create_user(name)
    token = generate_token()
    db.create_token(user.id, token, description="initial token")
    console.print(f"[green]✓ 用户已创建[/green]: {user.name}")
    console.print(f"[yellow]Token (只显示这一次):[/yellow] {token}")


@user_app.command("list")
def user_list():
    users = db.list_users()
    if not users:
        console.print("[dim]无用户[/dim]")
        return
    table = Table(title="Users")
    table.add_column("ID")
    table.add_column("Name")
    table.add_column("Created")
    for u in users:
        table.add_row(str(u.id), u.name, u.created_at)
    console.print(table)


# ---------- token ----------

@token_app.command("create")
def token_create(user_name: str, description: str = ""):
    user = db.get_user_by_name(user_name)
    if not user:
        console.print(f"[red]用户 '{user_name}' 不存在[/red]")
        raise typer.Exit(1)
    token = generate_token()
    db.create_token(user.id, token, description=description or None)
    console.print(f"[yellow]Token (只显示这一次):[/yellow] {token}")


@token_app.command("revoke")
def token_revoke(token: str):
    if db.revoke_token(token):
        console.print("[green]✓ 已吊销[/green]")
    else:
        console.print("[red]Token 不存在[/red]")
        raise typer.Exit(1)


# ---------- repo ----------

@repo_app.command("create")
def repo_create(name: str, owner: str, private: bool = typer.Option(False, "--private")):
    """创建仓库（CLI 直接调，不需要 Token）。"""
    from . import storage
    user = db.get_user_by_name(owner)
    if not user:
        console.print(f"[red]Owner '{owner}' 不存在[/red]")
        raise typer.Exit(1)
    if db.get_repo(name):
        console.print(f"[red]仓库 '{name}' 已存在[/red]")
        raise typer.Exit(1)
    try:
        storage.create_bare_repo(name)
    except storage.RepoStorageError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    db.create_repo(name, owner_id=user.id, is_private=private)
    console.print(f"[green]✓ 仓库已创建[/green]: {name}")
    console.print(f"  路径: {storage.repo_path(name)}")


@repo_app.command("list")
def repo_list():
    repos = db.list_repos()
    if not repos:
        console.print("[dim]无仓库[/dim]")
        return
    table = Table(title="Repositories")
    table.add_column("Name")
    table.add_column("Owner")
    table.add_column("Private")
    table.add_column("Created")
    for r in repos:
        owner = db.get_user_by_id(r.owner_id)
        table.add_row(
            r.name,
            owner.name if owner else "<orphan>",
            "Yes" if r.is_private else "No",
            r.created_at,
        )
    console.print(table)


@repo_app.command("delete")
def repo_delete(name: str):
    from . import storage
    if not db.get_repo(name):
        console.print(f"[red]仓库 '{name}' 不存在[/red]")
        raise typer.Exit(1)
    db.delete_repo(name)
    storage.delete_bare_repo(name)
    console.print(f"[green]✓ 仓库已删除[/green]: {name}")


if __name__ == "__main__":
    app()
