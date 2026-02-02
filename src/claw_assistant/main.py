"""CLI 入口：serve / run / status / approve / reject。"""

import typer
from httpx import Client, HTTPStatusError

DEFAULT_BASE = "http://localhost:8080"

app = typer.Typer(help="claw-assistant: Human-in-the-Loop AI execution and governance")


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", "--host", "-H", help="bind host"),
    port: int = typer.Option(8080, "--port", "-p", help="bind port"),
) -> None:
    """启动本地 HTTP daemon（默认 localhost:8080）。"""
    import uvicorn
    from claw_assistant.server.app import create_app

    uvicorn.run(create_app(), host=host, port=port)


@app.command()
def run(
    intent: str = typer.Argument(..., help="任务意图，如：发布一条测试"),
    base: str = typer.Option(DEFAULT_BASE, "--base", "-b", help="daemon 基地址"),
) -> None:
    """向 daemon 发起一次任务流；若需审批会挂起直到 approve/reject。"""
    with Client(base_url=base, timeout=300.0, trust_env=False) as client:
        try:
            r = client.post("/run", json={"intent": intent})
            r.raise_for_status()
            data = r.json()
            if data.get("ok"):
                typer.echo("执行完成:")
                typer.echo(data.get("result", data))
            else:
                typer.echo("执行失败:", err=True)
                typer.echo(data, err=True)
                raise typer.Exit(1)
        except HTTPStatusError as e:
            typer.echo(f"请求失败: {e.response.status_code} {e.response.text}", err=True)
            raise typer.Exit(1)


@app.command()
def status(
    base: str = typer.Option(DEFAULT_BASE, "--base", "-b", help="daemon 基地址"),
) -> None:
    """列出当前待审批。"""
    with Client(base_url=base, timeout=10.0, trust_env=False) as client:
        try:
            r = client.get("/status")
            r.raise_for_status()
            data = r.json()
            pending = data.get("pending", [])
            if not pending:
                typer.echo("无待审批")
                return
            for p in pending:
                typer.echo(
                    f"  {p.get('approval_id')}  {p.get('tool_name')}  {p.get('summary', '')[:50]}"
                )
        except HTTPStatusError as e:
            typer.echo(f"请求失败: {e.response.status_code} {e.response.text}", err=True)
            raise typer.Exit(1)


def _resolve(approval_id: str, path: str, base: str, label: str) -> None:
    with Client(base_url=base, timeout=10.0, trust_env=False) as client:
        try:
            r = client.post(path, json={"approval_id": approval_id})
            r.raise_for_status()
            typer.echo(f"已{label}: {approval_id}")
        except HTTPStatusError as e:
            typer.echo(f"请求失败: {e.response.status_code} {e.response.text}", err=True)
            raise typer.Exit(1)


@app.command()
def approve(
    approval_id: str = typer.Argument(..., help="待审批 ID"),
    base: str = typer.Option(DEFAULT_BASE, "--base", "-b", help="daemon 基地址"),
) -> None:
    """通过审批。"""
    _resolve(approval_id, "/approve", base, "通过审批")


@app.command()
def reject(
    approval_id: str = typer.Argument(..., help="待审批 ID"),
    base: str = typer.Option(DEFAULT_BASE, "--base", "-b", help="daemon 基地址"),
) -> None:
    """拒绝审批。"""
    _resolve(approval_id, "/reject", base, "拒绝审批")


if __name__ == "__main__":
    app()
