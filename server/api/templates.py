"""模板 API。"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..store import repo
from ..store.schema import CanvasSpec, Template

router = APIRouter(tags=["templates"])


class TemplateCreate(BaseModel):
    """新建模板。`canvas` 用于让用户直接选常见卡牌尺寸（见 web/src/constants/cardSizes.ts）。"""
    name: Optional[str] = None
    fromId: Optional[str] = None
    canvas: Optional[Dict[str, Any]] = None


def _apply_canvas(t: Template, cv: Optional[Dict[str, Any]]) -> None:
    """把用户选的物理尺寸写进 canvas；像素值做合法性夹取，避免手滑填出荒唐尺寸。"""
    if not cv:
        return
    data = t.canvas.model_dump()
    for k in ("w", "h", "dpi", "bleed", "w_mm", "h_mm"):
        if cv.get(k) is not None:
            data[k] = cv[k]
    data["w"] = int(max(64, min(8192, data["w"])))
    data["h"] = int(max(64, min(8192, data["h"])))
    data["dpi"] = int(max(72, min(1200, data["dpi"])))
    data["bleed"] = int(max(0, data["bleed"]))
    t.canvas = CanvasSpec(**data)


@router.get("/api/projects/{pid}/templates")
def index(pid: str):
    return repo.list_templates(pid)


@router.post("/api/projects/{pid}/templates")
def create(pid: str, from_id: Optional[str] = None, name: Optional[str] = None,
           body: Optional[TemplateCreate] = None):
    """新建模板。支持 `?from_id=`（复制）与 body 里的 `canvas`（选卡牌尺寸）。"""
    fid = (body.fromId if body and body.fromId else from_id)
    nm = ((body.name if body and body.name else name) or "").strip()
    cv = body.canvas if body else None
    if fid:
        src = repo.get_template(pid, fid)
        if not src:
            raise HTTPException(404, "源模板不存在")
        data = src.model_dump()
        data["id"] = Template().id
        data["name"] = nm or f"{src.name} 副本"
        data["version"] = 1
        t = Template(**data)
    else:
        t = Template(projectId=pid, name=nm or "新模板")
    _apply_canvas(t, cv)
    t.projectId = pid
    repo.save_template(t)
    return t.model_dump()


@router.get("/api/templates/{tid}")
def detail(tid: str, pid: Optional[str] = None):
    t = _find(pid, tid)
    return t.model_dump()


@router.put("/api/templates/{tid}")
def update(tid: str, body: dict):
    cur = _find(body.get("projectId"), tid)
    data = cur.model_dump()
    data.update({k: v for k, v in body.items()
                 if k not in ("id", "projectId", "createdAt")})
    t = Template(**data)
    repo.save_template(t)
    return t.model_dump()


@router.delete("/api/templates/{tid}")
def delete(tid: str, pid: Optional[str] = None):
    cur = _find(pid, tid)
    repo.delete_template(cur.projectId, tid)
    return {"ok": True}


def _find(pid: Optional[str], tid: str) -> Template:
    if pid:
        t = repo.get_template(pid, tid)
        if t:
            return t
    # 未传 pid 时全库查找（模板 id 全局唯一）
    for d in repo.config.PROJECTS_DIR.iterdir():
        t = repo.get_template(d.name, tid)
        if t:
            return t
    raise HTTPException(404, "模板不存在")
