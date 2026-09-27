"""卡牌 API：CRUD + JSON/CSV 批量导入（显式字段映射）。"""
from __future__ import annotations

import csv
import io
import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from ..store import repo
from ..store.schema import Card, now_iso

router = APIRouter(tags=["cards"])


class CardCreate(BaseModel):
    templateId: str
    name: str = "新卡牌"
    fields: Dict[str, Any] = {}
    tags: List[str] = []


class ImportBody(BaseModel):
    templateId: str
    format: str = "json"          # json | csv
    payload: str                  # JSON 文本或 CSV 文本
    mapping: Dict[str, str] = {}  # CSV: {表头 -> 字段 key}
    nameKey: Optional[str] = None  # 用哪个字段作为卡名
    mode: str = "append"          # append | replace


class BulkUpdateBody(BaseModel):
    """表格批量模式的保存载荷：只传改过的卡。"""
    cards: List[Dict[str, Any]] = []


class BulkDeleteBody(BaseModel):
    """批量删除载荷（卡片 Tab 勾选后一次删掉）。"""
    ids: List[str] = []


@router.get("/api/projects/{pid}/cards")
def index(pid: str, q: str = "", tag: str = "", templateId: str = "",
          full: bool = False):
    """full=false 返回轻量索引（无 fields，列表快）；full=true 返回完整卡牌
    （表格批量编辑需要逐格取值，用它）。"""
    rows = repo.list_cards(pid, q=q, tag=tag, template_id=templateId)
    if not full:
        return rows
    out = []
    for e in rows:
        c = repo.get_card(pid, e["id"])
        out.append(c.model_dump() if c else e)
    return out


@router.post("/api/projects/{pid}/cards")
def create(pid: str, body: CardCreate):
    tpl = repo.get_template(pid, body.templateId)
    if not tpl:
        raise HTTPException(404, "模板不存在")
    fields = dict(body.fields)
    for fd in tpl.fields:
        if fd.binding == "fixed":
            fields.setdefault(fd.key, fd.value)
        else:
            fields.setdefault(fd.key, fd.constraint.default)
    c = Card(projectId=pid, templateId=body.templateId,
             name=body.name, fields=fields, tags=body.tags)
    repo.save_card(c)
    return c.model_dump()


@router.get("/api/cards/{cid}")
def detail(cid: str, pid: Optional[str] = None):
    card = _find(pid, cid)
    return card.model_dump()


@router.put("/api/cards/{cid}")
def update(cid: str, body: dict):
    cur = _find(body.get("projectId"), cid)
    data = cur.model_dump()
    data.update({k: v for k, v in body.items()
                 if k not in ("id", "projectId", "createdAt")})
    data["version"] = cur.version + 1
    repo.save_card(Card(**data))
    return data


@router.delete("/api/cards/{cid}")
def delete(cid: str, pid: Optional[str] = None):
    cur = _find(pid, cid)
    repo.delete_card(cur.projectId, cid)
    return {"ok": True}


@router.post("/api/projects/{pid}/cards/bulk-delete")
def bulk_delete(pid: str, body: BulkDeleteBody):
    """一次删掉多张卡（前端勾选后调用）。

    放后端批量做而不是前端循环 delete：一次请求、一次索引重建，
    删 100 张也不会打出 100 个请求。不存在的 id 直接跳过，返回真实删除数。
    """
    n = 0
    for cid in body.ids:
        if repo.get_card(pid, cid):
            repo.delete_card(pid, cid)
            n += 1
    return {"deleted": n}


# --------------------------------------------------------------------------
# 表格批量模式的保存 + 数据导出（§P5-E3）
# --------------------------------------------------------------------------
@router.post("/api/projects/{pid}/cards/bulk-update")
def bulk_update(pid: str, body: BulkUpdateBody):
    n = 0
    for item in body.cards:
        cid = item.get("id")
        if not cid:
            continue
        cur = repo.get_card(pid, cid)
        if not cur:
            continue
        data = cur.model_dump()
        if "name" in item:
            data["name"] = str(item["name"])
        if "tags" in item:
            data["tags"] = list(item["tags"] or [])
        if "fields" in item:
            data["fields"] = {**(data.get("fields") or {}), **(item["fields"] or {})}
        data["version"] = cur.version + 1
        data["updatedAt"] = now_iso()
        repo.save_card(Card(**data))
        n += 1
    return {"updated": n}


@router.get("/api/projects/{pid}/cards/export")
def export_data(pid: str, format: str = "json", templateId: str = ""):
    """导出卡牌数据。CSV 为扁平化一行一卡，可直接改完再导入（闭环）。"""
    # list_cards 返回的是轻量索引（不含 fields），导出必须取完整对象
    cards = []
    for row in repo.list_cards(pid, template_id=templateId):
        obj = repo.get_card(pid, row["id"])
        cards.append(obj.model_dump() if obj else row)
    if format == "csv":
        keys: List[str] = []
        for c in cards:
            for k in (c.get("fields") or {}):
                if k not in keys:
                    keys.append(k)
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["name", "tags", *keys])
        for c in cards:
            w.writerow([c.get("name", ""), "|".join(c.get("tags") or []),
                        *[(c.get("fields") or {}).get(k, "") for k in keys]])
        return PlainTextResponse(
            buf.getvalue(), media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="cards.csv"'})
    return {"cards": cards}


# --------------------------------------------------------------------------
# 批量导入
# --------------------------------------------------------------------------
@router.post("/api/projects/{pid}/cards/import")
def import_cards(pid: str, body: ImportBody):
    tpl = repo.get_template(pid, body.templateId)
    if not tpl:
        raise HTTPException(404, "模板不存在")

    if body.mode == "replace":
        for e in repo.list_cards(pid, template_id=body.templateId):
            repo.delete_card(pid, e["id"])

    if body.format == "json":
        rows = _parse_json(body.payload)
    else:
        rows = _parse_csv(body.payload, body.mapping)

    created = []
    for row in rows:
        fields: Dict[str, Any] = {}
        for fd in tpl.fields:
            if fd.binding == "fixed":
                fields[fd.key] = fd.value
                continue
            v = row.get(fd.key, row.get(fd.label, fd.constraint.default))
            fields[fd.key] = _coerce(v, fd.constraint.type)
        name = row.get("name") or row.get("卡名")
        if body.nameKey:
            name = row.get(body.nameKey) or name
        c = Card(projectId=pid, templateId=body.templateId,
                 name=str(name or "未命名"), fields=fields)
        repo.save_card(c)
        created.append(c.model_dump())
    return {"created": len(created), "cards": created}


def _parse_json(text: str) -> List[Dict[str, Any]]:
    data = json.loads(text)
    if isinstance(data, dict):
        data = data.get("cards", [])
    if not isinstance(data, list):
        raise HTTPException(400, "JSON 必须是数组或 {cards: []}")
    return data


def _parse_csv(text: str, mapping: Dict[str, str]) -> List[Dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(text))
    rows = []
    for raw in reader:
        row: Dict[str, Any] = {}
        for header, value in raw.items():
            if header is None:
                continue
            # 显式映射优先；映射成空串 = 忽略这一列；否则按表头直配
            key = mapping.get(header, header)
            if not key:
                continue
            row[key] = value
        rows.append(row)
    return rows


def _coerce(v: Any, type_: str):
    if v is None or v == "":
        return None
    try:
        if type_ == "int":
            return int(float(v))
        if type_ == "float":
            return float(v)
        if type_ == "bool":
            return str(v).lower() in ("1", "true", "yes", "是")
    except (TypeError, ValueError):
        return v
    return v


def _find(pid: Optional[str], cid: str) -> Card:
    if pid:
        c = repo.get_card(pid, cid)
        if c:
            return c
    for d in repo.config.PROJECTS_DIR.iterdir():
        c = repo.get_card(d.name, cid)
        if c:
            return c
    raise HTTPException(404, "卡牌不存在")
