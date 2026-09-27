"""资源 API：icon 子库 / 字体 / 图片 / 底板。"""
from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from .. import config
from ..store import repo
from ..store.schema import AssetItem
from ..util import thumbs

router = APIRouter(prefix="/api", tags=["assets"])

MEDIA = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".webp": "image/webp", ".gif": "image/gif", ".bmp": "image/bmp",
    ".svg": "image/svg+xml", ".ttf": "font/ttf", ".otf": "font/otf",
    ".woff2": "font/woff2",
}


@router.get("/asset-libraries")
def libraries():
    return repo.asset_libraries()


@router.get("/assets")
def index(type: str = "", library: str = "", q: str = ""):
    return repo.list_assets(type_=type, library=library, q=q)


@router.post("/assets/upload")
async def upload(file: UploadFile = File(...), type: str = Form("image"),
                 library: str = Form(""), name: str = Form(""),
                 tags: str = Form("")):
    ext = "." + (file.filename or "x").rsplit(".", 1)[-1].lower()
    if ext not in MEDIA:
        raise HTTPException(400, f"不支持的文件类型：{ext}")
    a = AssetItem(type=type, name=name or (file.filename or "资源"),
                  library=library or None, ext=ext,
                  tags=[t for t in tags.split(",") if t.strip()],
                  colorable=(ext == ".svg"))
    dest = config.ASSETS_DIR / a.rel_path
    dest.parent.mkdir(parents=True, exist_ok=True)
    content = await file.read()
    dest.write_bytes(content)
    a.size = len(content)
    repo.add_asset(a)
    # 图片 / 底板顺手生成缩略图（SVG 与字体不做，make_thumb 内部会静默跳过）
    if type in ("image", "baseplate") and ext != ".svg":
        thumbs.make_thumb(dest, config.ASSETS_DIR, a.id)
    return a.model_dump()


@router.get("/assets/{aid}/thumb")
def get_thumb(aid: str):
    """缩略图（列表用）。没有缩略图就退回原文件，前端可以无条件用它。

    历史资源（缩略图功能上线前上传 / AI 生成的）在这里**懒生成**一次，
    不用另外跑迁移脚本去动用户的数据。
    """
    a = repo.get_asset(aid)
    if not a:
        raise HTTPException(404, "资源不存在")
    t = thumbs.thumb_path(config.ASSETS_DIR, aid)
    p = config.ASSETS_DIR / a.rel_path
    if not t.exists() and a.type in ("image", "baseplate") and a.ext != ".svg" and p.exists():
        thumbs.make_thumb(p, config.ASSETS_DIR, aid)
    if t.exists():
        return FileResponse(t, media_type="image/jpeg")
    if not p.exists():
        raise HTTPException(404, "文件已丢失")
    return FileResponse(p, media_type=MEDIA.get(a.ext, "application/octet-stream"))


@router.get("/assets/{aid}/file")
def get_file(aid: str):
    a = repo.get_asset(aid)
    if not a:
        raise HTTPException(404, "资源不存在")
    p = config.ASSETS_DIR / a.rel_path
    if not p.exists():
        raise HTTPException(404, "文件已丢失")
    return FileResponse(p, media_type=MEDIA.get(a.ext, "application/octet-stream"))


@router.delete("/assets/{aid}")
def delete(aid: str):
    if not repo.delete_asset(aid):
        raise HTTPException(404, "资源不存在")
    return {"ok": True}
