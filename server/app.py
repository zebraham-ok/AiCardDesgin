"""桌游设计工作坊 —— 本地服务端入口。

启动：
    python run.py
    # 或
    python -m server.app
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .ai import jobs
from .api import ai, assets, cards, exports, projects, templates
from .util import seed

app = FastAPI(title="桌游设计工作坊", version="0.1.0")

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"])

for r in (projects.router, templates.router, cards.router, assets.router,
          exports.router, ai.router):
    app.include_router(r)


@app.get("/api/health")
def health():
    return {"ok": True, "workspace": str(config.WORKSPACE),
            "ai": {"openlux": bool(config.OPENLUX_KEY),
                   "aliyunMultimodal": bool(config.ALIYUN_MULTIMODAL_KEY),
                   "aliyunText": bool(config.ALIYUN_TEXT_KEY)}}


@app.on_event("startup")
def on_startup():
    # 只做数据初始化；不打开浏览器（否则 TestClient / 导入即会拉起浏览器）
    seed.seed_icons()
    seed.seed_demo_project()
    # 上次进程留下的 running 任务标成 interrupted，否则前端永远转圈
    jobs.load_on_startup()


# --------------------------------------------------------------------------
# 前端静态托管（生产构建产物 web/dist）
# --------------------------------------------------------------------------
DIST = config.ROOT / "web" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")
    app.mount("/icons", StaticFiles(directory=config.ASSETS_DIR / "icons"),
              name="icons")

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        target = DIST / full_path
        if full_path and target.exists() and target.is_file():
            return FileResponse(target)
        return FileResponse(DIST / "index.html")
else:
    @app.get("/{full_path:path}")
    def no_build(full_path: str):
        return JSONResponse(
            {"error": "前端未构建，请先执行：cd web && npm install && npm run build"},
            status_code=503)
