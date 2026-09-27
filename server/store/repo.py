"""JSON 文件仓储实现。

设计要点：
  * 所有写操作走原子写（tmp + os.replace），写前留 .bak 快照
  * 卡牌列表走 cards/_index.json，避免打开项目时读上千个文件
  * 上层只依赖这里的函数；日后换 SQLite 只需替换本文件
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .. import config
from .schema import (AssetItem, Card, Project, Template, new_id, now_iso)


# --------------------------------------------------------------------------
# 原子读写
# --------------------------------------------------------------------------
def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        bak = path.with_suffix(path.suffix + ".bak")
        if bak.exists():
            try:
                return json.loads(bak.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass
        return default


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        try:
            shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))
        except OSError:
            pass
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(payload)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


# --------------------------------------------------------------------------
# 路径
# --------------------------------------------------------------------------
def project_dir(pid: str) -> Path:
    return config.PROJECTS_DIR / pid


def templates_dir(pid: str) -> Path:
    return project_dir(pid) / "templates"


def template_dir(pid: str, tid: str) -> Path:
    return templates_dir(pid) / tid


def cards_dir(pid: str) -> Path:
    return project_dir(pid) / "cards"


# --------------------------------------------------------------------------
# Project
# --------------------------------------------------------------------------
def list_projects() -> List[Dict[str, Any]]:
    out = []
    for d in sorted(config.PROJECTS_DIR.iterdir(), key=lambda p: p.name):
        pj = d / "project.json"
        if not (d.is_dir() and pj.exists()):
            continue
        data = read_json(pj)
        if not data:
            continue
        idx = read_json(cards_dir(d.name) / "_index.json", [])
        tpl_count = len([p for p in templates_dir(d.name).iterdir()
                         if p.is_dir() and (p / "template.json").exists()]) \
            if templates_dir(d.name).exists() else 0
        out.append({**data, "cardCount": len(idx), "templateCount": tpl_count})
    return out


def get_project(pid: str) -> Optional[Project]:
    data = read_json(project_dir(pid) / "project.json")
    return Project(**data) if data else None


def save_project(p: Project) -> Project:
    p.updatedAt = now_iso()
    write_json(project_dir(p.id) / "project.json", p.model_dump())
    return p


def delete_project(pid: str) -> bool:
    d = project_dir(pid)
    if not d.exists():
        return False
    shutil.rmtree(d)
    return True


def duplicate_project(pid: str, name: Optional[str] = None) -> Optional[Project]:
    src = project_dir(pid)
    if not src.exists():
        return None
    p = get_project(pid)
    new_pid = new_id("p")
    dst = project_dir(new_pid)
    shutil.copytree(src, dst)
    data = read_json(dst / "project.json")
    data["id"] = new_pid
    data["name"] = name or f"{p.name} 副本"
    data["createdAt"] = now_iso()
    # 模板/卡牌的 projectId 需要重写
    for td in templates_dir(new_pid).iterdir():
        tf = td / "template.json"
        if tf.exists():
            t = read_json(tf)
            t["projectId"] = new_pid
            write_json(tf, t)
    cd = cards_dir(new_pid)
    idx = read_json(cd / "_index.json", [])
    for entry in idx:
        cf = cd / f"{entry['id']}.json"
        if cf.exists():
            c = read_json(cf)
            c["projectId"] = new_pid
            write_json(cf, c)
    write_json(dst / "project.json", data)
    return Project(**data)


# --------------------------------------------------------------------------
# Template
# --------------------------------------------------------------------------
def list_templates(pid: str) -> List[Dict[str, Any]]:
    td = templates_dir(pid)
    out = []
    if not td.exists():
        return out
    idx = {e["id"]: e for e in read_json(cards_dir(pid) / "_index.json", [])}
    for d in sorted(td.iterdir(), key=lambda p: p.stat().st_mtime):
        tf = d / "template.json"
        if d.is_dir() and tf.exists():
            data = read_json(tf)
            if not data:
                continue
            used = sum(1 for e in idx.values() if e.get("templateId") == data["id"])
            out.append({**data, "cardCount": used})
    return out


def get_template(pid: str, tid: str) -> Optional[Template]:
    data = read_json(template_dir(pid, tid) / "template.json")
    return Template(**data) if data else None


def save_template(t: Template) -> Template:
    t.projectId = t.projectId or ""
    t.updatedAt = now_iso()
    write_json(template_dir(t.projectId, t.id) / "template.json", t.model_dump())
    return t


def delete_template(pid: str, tid: str) -> bool:
    d = template_dir(pid, tid)
    if not d.exists():
        return False
    shutil.rmtree(d)
    return True


# --------------------------------------------------------------------------
# Card
# --------------------------------------------------------------------------
def _rebuild_index(pid: str) -> List[Dict[str, Any]]:
    cd = cards_dir(pid)
    idx = []
    if not cd.exists():
        return idx
    for f in cd.glob("*.json"):
        if f.name == "_index.json":
            continue
        data = read_json(f)
        if not data:
            continue
        idx.append({"id": data.get("id"), "name": data.get("name", ""),
                    "templateId": data.get("templateId", ""),
                    "tags": data.get("tags", []),
                    "updatedAt": data.get("updatedAt", "")})
    idx.sort(key=lambda e: e.get("updatedAt", ""), reverse=True)
    write_json(cd / "_index.json", idx)
    return idx


def list_cards(pid: str, q: str = "", tag: str = "",
               template_id: str = "") -> List[Dict[str, Any]]:
    idx = read_json(cards_dir(pid) / "_index.json", None)
    if idx is None:
        idx = _rebuild_index(pid)
    q = (q or "").strip().lower()
    out = []
    for e in idx:
        if template_id and e.get("templateId") != template_id:
            continue
        if tag and tag not in (e.get("tags") or []):
            continue
        if q and q not in (e.get("name") or "").lower():
            continue
        out.append(e)
    return out


def get_card(pid: str, cid: str) -> Optional[Card]:
    data = read_json(cards_dir(pid) / f"{cid}.json")
    return Card(**data) if data else None


def save_card(c: Card) -> Card:
    c.updatedAt = now_iso()
    write_json(cards_dir(c.projectId) / f"{c.id}.json", c.model_dump())
    _rebuild_index(c.projectId)
    return c


def save_cards_bulk(cards: List[Card]) -> List[Card]:
    for c in cards:
        c.updatedAt = now_iso()
        write_json(cards_dir(c.projectId) / f"{c.id}.json", c.model_dump())
    if cards:
        _rebuild_index(cards[0].projectId)
    return cards


def delete_card(pid: str, cid: str) -> bool:
    f = cards_dir(pid) / f"{cid}.json"
    if not f.exists():
        return False
    f.unlink()
    _rebuild_index(pid)
    return True


# --------------------------------------------------------------------------
# Stats
# --------------------------------------------------------------------------
def project_stats(pid: str) -> Dict[str, Any]:
    templates = list_templates(pid)
    cards = list_cards(pid)
    by_template: Dict[str, int] = {}
    for c in cards:
        by_template[c.get("templateId", "")] = \
            by_template.get(c.get("templateId", ""), 0) + 1

    # 数值/枚举字段分布
    distributions = []
    for t in templates:
        tpl = get_template(pid, t["id"])
        if not tpl:
            continue
        cards_of_tpl = [c for c in cards if c.get("templateId") == t["id"]]
        if not cards_of_tpl:
            continue
        numeric = []
        for fd in tpl.fields:
            if fd.kind in ("number", "enum"):
                values = []
                for c in cards_of_tpl:
                    card = get_card(pid, c["id"])
                    if card and fd.key in card.fields:
                        values.append(card.fields[fd.key])
                if values:
                    numeric.append({
                        "templateId": t["id"], "templateName": tpl.name,
                        "key": fd.key, "label": fd.label, "kind": fd.kind,
                        "options": fd.constraint.options,
                        "min": fd.constraint.min, "max": fd.constraint.max,
                        "values": values,
                    })
        distributions.extend(numeric)

    return {
        "cardCount": len(cards),
        "templateCount": len(templates),
        "byTemplate": by_template,
        "templates": [{"id": t["id"], "name": t["name"],
                       "cardCount": by_template.get(t["id"], 0),
                       "fieldCount": len(t.get("fields", [])),
                       "canvas": t.get("canvas")} for t in templates],
        "distributions": distributions,
    }


# --------------------------------------------------------------------------
# Assets（全局，跨项目共享）
# --------------------------------------------------------------------------
ASSETS_INDEX = config.ASSETS_DIR / "assets.json"


def list_assets(type_: str = "", library: str = "", q: str = "") -> List[Dict[str, Any]]:
    items = read_json(ASSETS_INDEX, [])
    q = (q or "").strip().lower()
    out = []
    for it in items:
        if type_ and it.get("type") != type_:
            continue
        if library and it.get("library") != library:
            continue
        if q:
            hay = " ".join([it.get("name", "")] + (it.get("tags") or [])).lower()
            if q not in hay:
                continue
        out.append(it)
    return out


def get_asset(aid: str) -> Optional[AssetItem]:
    for it in read_json(ASSETS_INDEX, []):
        if it.get("id") == aid:
            return AssetItem(**it)
    return None


def add_asset(a: AssetItem) -> AssetItem:
    items = read_json(ASSETS_INDEX, [])
    items.append(a.model_dump())
    write_json(ASSETS_INDEX, items)
    return a


def delete_asset(aid: str) -> bool:
    items = read_json(ASSETS_INDEX, [])
    target = next((i for i in items if i.get("id") == aid), None)
    if not target:
        return False
    f = config.ASSETS_DIR / AssetItem(**target).rel_path
    if f.exists():
        f.unlink()
    t = config.ASSETS_DIR / "thumbs" / f"{aid}.jpg"      # 缩略图一起清掉，别留孤儿
    if t.exists():
        t.unlink()
    write_json(ASSETS_INDEX, [i for i in items if i.get("id") != aid])
    return True


def asset_libraries() -> List[Dict[str, Any]]:
    """icon 子库一览（含内置 6 个子库）。"""
    builtin = [
        {"id": "elements", "name": "元素", "builtin": True},
        {"id": "resources", "name": "资源", "builtin": True},
        {"id": "status", "name": "状态", "builtin": True},
        {"id": "classes", "name": "职业", "builtin": True},
        {"id": "arrows", "name": "箭头指示", "builtin": True},
        {"id": "numeric", "name": "数值骰子", "builtin": True},
    ]
    counts: Dict[str, int] = {}
    for it in list_assets(type_="icon"):
        lib = it.get("library") or "misc"
        counts[lib] = counts.get(lib, 0) + 1
    for b in builtin:
        b["count"] = counts.get(b["id"], 0)
    extra = [{"id": k, "name": k, "builtin": False, "count": v}
             for k, v in counts.items() if k not in {b["id"] for b in builtin}]
    return builtin + extra
