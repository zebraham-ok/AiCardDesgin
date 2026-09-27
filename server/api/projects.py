"""项目 API（首页 = 多项目；项目管理页 = 单项目）。"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..store import repo
from ..store.schema import Project, ProjectBrief, now_iso

router = APIRouter(prefix="/api/projects", tags=["projects"])


class ProjectCreate(BaseModel):
    name: str
    description: str = ""
    tags: List[str] = []


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    cover: Optional[str] = None


@router.get("")
def index():
    return repo.list_projects()


@router.post("")
def create(body: ProjectCreate):
    p = Project(name=body.name, description=body.description, tags=body.tags)
    repo.save_project(p)
    return p.model_dump()


@router.get("/{pid}")
def detail(pid: str):
    p = repo.get_project(pid)
    if not p:
        raise HTTPException(404, "项目不存在")
    return p.model_dump()


@router.patch("/{pid}")
def update(pid: str, body: ProjectUpdate):
    p = repo.get_project(pid)
    if not p:
        raise HTTPException(404, "项目不存在")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(p, k, v)
    repo.save_project(p)
    return p.model_dump()


def _brief_is_empty(b: ProjectBrief) -> bool:
    """全空判定（用于"防误清空"）。"""
    a = b.artStyle
    return not any([b.title, b.subtitle, b.oneLiner, b.synopsis, b.players, b.playTime,
                    b.age, b.genre, b.keywords, b.taboos, b.factions,
                    a.style, a.palette, a.mood, a.references, a.details])


@router.put("/{pid}/brief")
def update_brief(pid: str, body: ProjectBrief, force: bool = False):
    """整体保存创作简报（§4.4）。前端表单一次性提交，后端做字段校验与去重。

    为什么不并进 PATCH：brief 是嵌套结构，PATCH 的浅合并会把 palette/factions
    这类数组整个替换掉，语义上容易误伤；这里用 PUT 明确「整份覆盖」。

    **防误清空**：若提交的是全空简报而服务器上已有内容，返回 409 要求显式 `force=true`。
    加这道闸是因为真出过事故 —— 一个脚本（冒烟测试）往项目里写 brief 再写 `{}`，
    把用户填好的设定静默冲掉了。有了它，任何"把非空设定清空"的操作都会先撞墙报错，
    而不是悄悄丢数据。
    """
    p = repo.get_project(pid)
    if not p:
        raise HTTPException(404, "项目不存在")
    if not force and _brief_is_empty(body) and not _brief_is_empty(p.brief):
        raise HTTPException(
            409, "当前项目设定不是空的，确认要清空它吗？确认后请带 force=true 再提交")
    b = body
    # 轻量清洗：去重保序 + 截断过长的列表，避免前端误传导致提示词爆炸
    b.keywords = _dedup(b.keywords)[:30]
    b.genre = _dedup(b.genre)[:12]
    b.taboos = _dedup(b.taboos)[:20]
    b.artStyle.palette = _dedup(b.artStyle.palette)[:6]
    b.artStyle.mood = _dedup(b.artStyle.mood)[:12]
    b.artStyle.references = _dedup(b.artStyle.references)[:12]
    b.factions = [f for f in b.factions if f.name.strip()][:20]
    b.updatedAt = now_iso()
    p.brief = b
    repo.save_project(p)
    return p.model_dump()


def _dedup(items: List[str]) -> List[str]:
    """去重保序 + 去空白项。"""
    out: List[str] = []
    for i in items or []:
        s = str(i).strip()
        if s and s not in out:
            out.append(s)
    return out


@router.delete("/{pid}")
def delete(pid: str):
    if not repo.delete_project(pid):
        raise HTTPException(404, "项目不存在")
    return {"ok": True}


@router.post("/{pid}/duplicate")
def duplicate(pid: str, name: Optional[str] = None):
    p = repo.duplicate_project(pid, name)
    if not p:
        raise HTTPException(404, "项目不存在")
    return p.model_dump()


@router.get("/{pid}/stats")
def stats(pid: str):
    return repo.project_stats(pid)
