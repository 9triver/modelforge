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

def _split_repo(repo: str) -> tuple[str, str]:
    if "/" not in repo:
        console.print(f"[red]仓库名必须是 'namespace/name' 格式[/red]: {repo}")
        raise typer.Exit(1)
    ns, name = repo.split("/", 1)
    if not ns or not name or "/" in name:
        console.print(f"[red]无效的仓库名[/red]: {repo}")
        raise typer.Exit(1)
    return ns, name


@repo_app.command("create")
def repo_create(repo: str, owner: str, private: bool = typer.Option(False, "--private")):
    """创建仓库。仓库名格式 'namespace/name'，例如 amazon/chronos-bolt-tiny。"""
    from . import storage
    namespace, name = _split_repo(repo)
    user = db.get_user_by_name(owner)
    if not user:
        console.print(f"[red]Owner '{owner}' 不存在[/red]")
        raise typer.Exit(1)
    if db.get_repo(namespace, name):
        console.print(f"[red]仓库 '{repo}' 已存在[/red]")
        raise typer.Exit(1)
    try:
        storage.create_bare_repo(namespace, name)
    except storage.RepoStorageError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    db.create_repo(namespace, name, owner_id=user.id, is_private=private)
    console.print(f"[green]✓ 仓库已创建[/green]: {repo}")
    console.print(f"  路径: {storage.repo_path(namespace, name)}")


@repo_app.command("list")
def repo_list():
    repos = db.list_repos()
    if not repos:
        console.print("[dim]无仓库[/dim]")
        return
    table = Table(title="Repositories")
    table.add_column("Repo")
    table.add_column("Owner")
    table.add_column("Private")
    table.add_column("Created")
    for r in repos:
        owner = db.get_user_by_id(r.owner_id)
        table.add_row(
            r.full_name,
            owner.name if owner else "<orphan>",
            "Yes" if r.is_private else "No",
            r.created_at,
        )
    console.print(table)


@repo_app.command("delete")
def repo_delete(repo: str):
    """删除仓库。仓库名格式 'namespace/name'。"""
    from . import storage
    namespace, name = _split_repo(repo)
    if not db.get_repo(namespace, name):
        console.print(f"[red]仓库 '{repo}' 不存在[/red]")
        raise typer.Exit(1)
    db.delete_repo(namespace, name)
    storage.delete_bare_repo(namespace, name)
    console.print(f"[green]✓ 仓库已删除[/green]: {repo}")


# ---------- run ----------

@app.command()
def run(
    repo: str = typer.Argument(..., help="仓库名 'namespace/name'"),
    input: str = typer.Option(..., "--input", "-i", help="输入文件/目录"),
    output: str = typer.Option(None, "--output", "-o", help="输出文件（默认 stdout）"),
    revision: str = typer.Option("main", "--revision", "-r"),
    endpoint: str = typer.Option(None, "--endpoint", envvar="MODELFORGE_URL"),
    token: str = typer.Option(None, "--token", envvar="MODELFORGE_TOKEN"),
):
    """下载模型并跑推理。

    Examples:
        modelforge run amazon/chronos-t5-tiny -i data.csv -o pred.csv
        modelforge run nateraw/vit-base-cats-vs-dogs -i images/ -o results.json
    """
    import json
    from pathlib import Path

    from .loader import load

    console.print(f"[cyan]Loading {repo}@{revision}...[/cyan]")
    handler = load(repo, revision=revision, endpoint=endpoint, token=token)
    task = handler.task
    console.print(f"[green]✓ Loaded[/green] task={task}")

    input_path = Path(input)
    if not input_path.exists():
        console.print(f"[red]输入不存在：{input_path}[/red]")
        raise typer.Exit(1)

    if task == "time-series-forecasting":
        import pandas as pd
        df = pd.read_csv(input_path)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        pred_df = handler.predict(df)
        if output:
            pred_df.to_csv(output, index=False)
            console.print(f"[green]✓ 写入 {output}[/green] ({len(pred_df)} 行)")
        else:
            console.print(pred_df.to_string(index=False))

    elif task == "image-classification":
        from PIL import Image as PILImage
        images = []
        paths = []
        if input_path.is_dir():
            for p in sorted(input_path.rglob("*")):
                if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp", ".webp"}:
                    images.append(PILImage.open(p).convert("RGB"))
                    paths.append(str(p))
        else:
            images.append(PILImage.open(input_path).convert("RGB"))
            paths.append(str(input_path))

        if not images:
            console.print("[red]未找到图片[/red]")
            raise typer.Exit(1)

        preds = handler.predict(images)
        results = []
        for path, pred in zip(paths, preds):
            top = pred[0] if pred else {"label": "?", "score": 0}
            results.append({"file": path, "label": top["label"], "score": top["score"]})

        if output:
            Path(output).write_text(json.dumps(results, indent=2, ensure_ascii=False))
            console.print(f"[green]✓ 写入 {output}[/green] ({len(results)} 张)")
        else:
            for r in results:
                console.print(f"  {r['file']}: {r['label']} ({r['score']:.4f})")

    elif task == "object-detection":
        from PIL import Image as PILImage
        images = []
        paths = []
        if input_path.is_dir():
            for p in sorted(input_path.rglob("*")):
                if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp", ".webp"}:
                    images.append(PILImage.open(p).convert("RGB"))
                    paths.append(str(p))
        else:
            images.append(PILImage.open(input_path).convert("RGB"))
            paths.append(str(input_path))

        if not images:
            console.print("[red]未找到图片[/red]")
            raise typer.Exit(1)

        preds = handler.predict(images)
        results = []
        for path, dets in zip(paths, preds):
            for d in dets:
                results.append({
                    "file": path,
                    "label": d["label"],
                    "bbox": d["bbox"],
                    "score": d["score"],
                })

        if output:
            Path(output).write_text(json.dumps(results, indent=2, ensure_ascii=False))
            console.print(f"[green]✓ 写入 {output}[/green] ({len(results)} 个检测)")
        else:
            for r in results:
                console.print(
                    f"  {r['file']}: {r['label']} ({r['score']:.4f}) "
                    f"bbox={[round(v,1) for v in r['bbox']]}"
                )
    else:
        console.print(f"[red]task '{task}' 的 CLI run 尚未支持[/red]")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
