"""GPT-Web-CF-Make 后端入口 - FastAPI 应用，Token 保活 + 注册机平台"""

from __future__ import annotations

import sys
from pathlib import Path

# 确保项目根目录在 sys.path
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# ── 创建 FastAPI 应用 ────────────────────────────────────────────────
app = FastAPI(
    title="GPT-Web-CF-Make",
    description="Token保活平台 - 使用refresh_token续期access_token，附带注册机能力",
    version="0.1.0",
)

# ── CORS 配置 ────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 注册路由 ─────────────────────────────────────────────────────────
from py.api.accounts import router as accounts_router
from py.api.tokens import router as tokens_router
from py.api.register import router as register_router
from py.api.settings import router as settings_router
from py.api.refresh_jobs import router as refresh_jobs_router
from py.api.proxy import router as proxy_router
from py.api.proxy_check import router as proxy_check_router
from py.api.proxy_pool import router as proxy_pool_router

app.include_router(accounts_router)
app.include_router(tokens_router)
app.include_router(register_router)
app.include_router(settings_router)
app.include_router(refresh_jobs_router)
app.include_router(proxy_router)
app.include_router(proxy_check_router)
app.include_router(proxy_pool_router)


# ── 健康检查 ─────────────────────────────────────────────────────────
@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}


# ── 静态文件 (前端构建产物) ──────────────────────────────────────────
_static_dir = ROOT_DIR / "web" / "dist"
if _static_dir.exists():
    app.mount("/", StaticFiles(directory=str(_static_dir), html=True), name="static")


@app.exception_handler(404)
async def spa_fallback(request: Request, exc):
    """让 React Router 的前端路径在生产环境可直接访问。"""
    index_file = _static_dir / "index.html"
    if not request.url.path.startswith("/api") and index_file.exists():
        return FileResponse(index_file)
    return JSONResponse({"detail": "Not Found"}, status_code=404)


def main():
    """启动 uvicorn 服务"""
    import uvicorn
    from py.services.config_service import config_service

    config = config_service.get()
    host = str(config.get("host") or "0.0.0.0")
    port = int(config.get("port") or 8787)

    uvicorn.run(
        "py.main:app",
        host=host,
        port=port,
        reload=True,
        log_level="info",
    )


if __name__ == "__main__":
    main()
