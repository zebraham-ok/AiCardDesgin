"""§P5-E3：项目包（zip）导出与导入 + 纯数据导出。

导出的一端在项目自治和用户自己手里：
  - 只打包本项目**实际引用到**的资源子集（默认），避免按 GB 计的图片目录被塞进 zip
  - `manifest.json` 记录 schemaVersion 与资源 sha1，导入端据此去重与校验
渲染不在服务端（浏览器 Fabric 渲染），所以这里只做打包 / 解包 / 数据导出。
"""
from __future__ import annotations

import hashlib
import io
import json
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from .. import config
from ..store import repo
from ..store.schema import AssetItem, now_iso, new_id

router = APIRouter(prefix="/api/projects", tags=["exports"])

MANIFEST_SCHEMA = 1


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------
def _asset_id(v: Any) -> Optional[str]:
    """从 asset://xxx 或裸 id 里取出资源 id。"""
    if not v or not isinstance(v, str):
        return None
    return v[8:] if v.startswith("asset://") else v


def _g(obj: Any, key: str) -> Any:
    """模板/卡牌里有些节点是 dict（如 background），有些是模型，统一取值。"""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def _font_asset_id(family: Any) -> Optional[str]:
    """`style.fontFamily` → 自定义字体 asset id。

    自定义字体在模板里存的是 `bgw_<assetId>`（见 web/src/render/fonts.ts 的 familyOf）。
    其余值（sans-serif、微软雅黑…）是系统/本机族名，没有对应 asset，返回 None。
    """
    if not isinstance(family, str) or not family.startswith("bgw_"):
        return None
    tail = family[4:]
    cand = tail if tail.startswith("as_") else f"as_{tail}"
    return cand if repo.get_asset(cand) else None


def _rel_path_of(a: Dict[str, Any]) -> Optional[str]:
    """资源落盘相对路径。

    包内清单优先；旧包没有 `rel_path`（它是 AssetItem 的派生属性，不在 model_dump 里）时，
    按 AssetItem 的规则从 id/ext/type 推导出来 —— 否则导入端会把整包资源判成"缺失"。
    """
    rel = a.get("rel_path") or a.get("relPath")
    if rel:
        return rel
    try:
        clean = {k: v for k, v in a.items() if k not in ("rel_path", "relPath")}
        return AssetItem(**clean).rel_path
    except Exception:
        return None


def _referenced_assets(pid: str) -> List[str]:
    """扫模板（底板 / 图层 / 字体 / 固定值字段）+ 卡牌字段值，得到本项目真正用到的资源 id。

    踩坑记录（G9）：早期只扫了 background 与 layers[].assetId，导致
      * **自定义字体不会被项目包带走**（字体是 `bgw_<id>` 写在 style.fontFamily 里的）；
      * `binding="fixed"` 字段的图片/图标值也被漏掉。
    跨机导入时表现为"字体回退、固定图丢失"。
    """
    ids: List[str] = []
    for t in repo.list_templates(pid):
        tpl = repo.get_template(pid, t["id"])
        if not tpl:
            continue
        a = _asset_id(_g(tpl.background, "assetId"))
        if a:
            ids.append(a)
        for l in tpl.layers:
            a = _asset_id(_g(l, "assetId"))
            if a:
                ids.append(a)
            fa = _font_asset_id(_g(_g(l, "style"), "fontFamily"))
            if fa:
                ids.append(fa)
        for f in tpl.fields:
            fa = _font_asset_id(_g(_g(f, "style"), "fontFamily"))
            if fa:
                ids.append(fa)
            # 固定值字段（模板锁定的图片 / 图标）
            if _g(f, "binding") == "fixed":
                a = _asset_id(_g(f, "value"))
                if a:
                    ids.append(a)
    image_like = {"image", "icon"}
    kinds: Dict[str, str] = {}
    for t in repo.list_templates(pid):
        tpl = repo.get_template(pid, t["id"])
        if not tpl:
            continue
        for f in tpl.fields:
            kinds[_g(f, "key")] = _g(f, "kind")
    for row in repo.list_cards(pid):
        c = repo.get_card(pid, row["id"])
        if not c:
            continue
        for k, v in (c.fields or {}).items():
            if kinds.get(k) in image_like or isinstance(v, str):
                a = _asset_id(v)
                if a:
                    ids.append(a)
    # 去重保序
    out: List[str] = []
    for i in ids:
        if i not in out:
            out.append(i)
    return out


def _sha1(b: bytes) -> str:
    return hashlib.sha1(b).hexdigest()


def _zip_project(pid: str, include_ai: bool, include_all_assets: bool,
                 include_exports: bool) -> Tuple[bytes, str, Dict[str, Any]]:
    """打包项目 → (zip 字节, 建议文件名, manifest)。"""
    proj = repo.get_project(pid)
    if not proj:
        raise HTTPException(404, "项目不存在")
    pdir = repo.project_dir(pid)
    pdata = repo.read_json(pdir / "project.json", {})

    if include_all_assets:
        asset_ids = [a["id"] for a in repo.list_assets()]
    else:
        asset_ids = [i for i in _referenced_assets(pid) if repo.get_asset(i)]

    buf = io.BytesIO()
    manifest: Dict[str, Any] = {
        "schemaVersion": MANIFEST_SCHEMA,
        "app": "boardgame-workshop",
        "exportedAt": datetime.now().isoformat(timespec="seconds"),
        "project": {"id": pdata.get("id"), "name": pdata.get("name")},
        "templates": 0, "cards": 0,
        "assets": [],
        "options": {
            "includeAI": include_ai,
            "includeAllAssets": include_all_assets,
            "includeExports": include_exports,
        },
    }
    missing: List[str] = []

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("project.json",
                   json.dumps(pdata, ensure_ascii=False, indent=2))

        # 模板（连同目录内的附属文件，如 base.png / preview.png）
        for t in repo.list_templates(pid):
            tdir = repo.template_dir(pid, t["id"])
            tf = tdir / "template.json"
            if not tf.exists():
                continue
            z.writestr(f"templates/{t['id']}/template.json", tf.read_text("utf-8"))
            manifest["templates"] += 1
            for extra in tdir.iterdir():
                if extra.name == "template.json" or extra.suffix == ".bak":
                    continue
                if extra.is_file():
                    z.writestr(f"templates/{t['id']}/{extra.name}",
                               extra.read_bytes())

        # 卡牌
        idx = repo.read_json(pdir / "cards" / "_index.json", [])
        z.writestr("cards/_index.json", json.dumps(idx, ensure_ascii=False, indent=2))
        for e in idx:
            cf = pdir / "cards" / f"{e['id']}.json"
            if cf.exists():
                z.writestr(f"cards/{e['id']}.json", cf.read_text("utf-8"))
                manifest["cards"] += 1

        # 资源（实际引用的子集）
        for aid in asset_ids:
            a = repo.get_asset(aid)
            if not a:
                missing.append(aid)
                continue
            src = config.ASSETS_DIR / a.rel_path
            if not src.exists():
                missing.append(aid)
                continue
            data = src.read_bytes()
            z.writestr(f"assets/{a.rel_path}", data)
            z.writestr(f"assets/{Path(a.rel_path).name}.meta.json",
                       json.dumps(a.model_dump(), ensure_ascii=False))
            manifest["assets"].append(
                {"id": a.id, "relPath": a.rel_path, "sha1": _sha1(data)})
        # 注意：`rel_path` 是 AssetItem 的派生属性，**不在 model_dump() 里**，
        # 必须显式写进包内清单，否则导入端拿不到资源落盘路径（曾导致整包资源被判缺失）。
        z.writestr("assets/assets.json", json.dumps(
            [{**repo.get_asset(i).model_dump(), "rel_path": repo.get_asset(i).rel_path}
             for i in asset_ids if repo.get_asset(i)],
            ensure_ascii=False, indent=2))

        # AI 任务与溯源
        if include_ai:
            jdir = pdir / "jobs"
            if jdir.exists():
                for f in jdir.rglob("*"):
                    if f.is_file() and f.suffix != ".bak":
                        z.writestr(f"jobs/{f.relative_to(jdir).as_posix()}",
                                   f.read_bytes())

        if include_exports:
            edir = pdir / "exports"
            if edir.exists():
                for f in edir.rglob("*"):
                    if f.is_file():
                        z.writestr(f"exports/{f.relative_to(edir).as_posix()}",
                                   f.read_bytes())

        manifest["missingAssets"] = missing
        z.writestr("manifest.json",
                   json.dumps(manifest, ensure_ascii=False, indent=2))

    name = f"{pdata.get('name') or 'project'}_{pid}.zip".replace("/", "_")
    return buf.getvalue(), name, manifest


def _unzip(bytes_: bytes) -> Dict[str, bytes]:
    """解包 → {相对路径: 字节}（兼容 zip 里多一层根目录）"""
    files: Dict[str, bytes] = {}
    with zipfile.ZipFile(io.BytesIO(bytes_)) as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            files[info.filename] = z.read(info.filename)
    # 兼容「zip 里带一层根目录」的情况
    top = {k.split("/", 1)[0] for k in files}
    if len(top) == 1 and "manifest.json" not in files:
        prefix = top.pop() + "/"
        files = {k[len(prefix):]: v for k, v in files.items() if k.startswith(prefix)}
    return files


@router.get("/{pid}/export/package")
def export_package(
    pid: str,
    includeAI: bool = True,
    includeAllAssets: bool = False,
    includeExports: bool = False,
):
    """打包整个项目（含 manifest.json 与实际引用的资源）。"""
    from urllib.parse import quote
    data, name, _ = _zip_project(pid, includeAI, includeAllAssets, includeExports)
    # HTTP 头是 latin-1，中文名要走 RFC 5987 filename*=UTF-8''%xx
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/zip",
        headers={"Content-Disposition":
                 f"attachment; filename=\"{pid}.zip\"; "
                 f"filename*=UTF-8''{quote(name)}"})


@router.post("/import-package")
async def import_package(
    file: UploadFile = File(...),
    conflict: str = "rename",   # rename | overwrite | cancel
):
    """导入项目包。资源按 sha1 去重：本地已有则复用，缺失项记进 missingAssets。"""
    raw = await file.read()
    try:
        files = _unzip(raw)
    except zipfile.BadZipFile:
        raise HTTPException(400, "不是有效的 zip 包")

    manifest = json.loads(files.get("manifest.json", b"{}") or b"{}")
    if manifest and manifest.get("schemaVersion") not in (None, MANIFEST_SCHEMA):
        raise HTTPException(400, f"不支持的包版本：{manifest.get('schemaVersion')}")
    pdata = json.loads(files.get("project.json", b"{}") or b"{}")
    if not pdata:
        raise HTTPException(400, "包里没有 project.json，无法导入")

    # 同名冲突策略
    existing = [p for p in repo.list_projects() if p.get("name") == pdata.get("name")]
    if existing and conflict == "cancel":
        raise HTTPException(409, f"已存在同名项目「{pdata.get('name')}」，"
                                 "请选择追加后缀或覆盖")
    if existing and conflict == "overwrite":
        for e in existing:
            repo.delete_project(e["id"])

    old_pid = pdata.get("id")
    new_pid = old_pid
    if not new_pid or repo.project_dir(new_pid).exists():
        new_pid = new_id("p")
    if existing and conflict == "rename":
        n = 2
        while any(p.get("name") == f"{pdata.get('name')} {n}" for p in repo.list_projects()):
            n += 1
        pdata["name"] = f"{pdata.get('name')} {n}"

    pdata["id"] = new_pid
    pdata["createdAt"] = pdata.get("createdAt") or now_iso()
    dst = repo.project_dir(new_pid)
    dst.mkdir(parents=True, exist_ok=True)
    repo.write_json(dst / "project.json", pdata)

    templates_n = 0
    for key, blob in files.items():
        parts = key.split("/")
        if parts[0] == "templates" and len(parts) >= 3:
            target = dst / "templates" / "/".join(parts[1:])
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(blob)
            if parts[-1] == "template.json":
                templates_n += 1
                if old_pid and old_pid != new_pid:
                    d = json.loads(blob.decode("utf-8"))
                    d["projectId"] = new_pid
                    target.write_text(json.dumps(d, ensure_ascii=False, indent=2), "utf-8")

    cards_n = 0
    for key, blob in files.items():
        parts = key.split("/")
        if parts[0] == "cards" and len(parts) == 2:
            if parts[1] == "_index.json":
                continue
            d = json.loads(blob.decode("utf-8"))
            d["projectId"] = new_pid
            repo.write_json(dst / "cards" / parts[1], d)
            cards_n += 1

    # 资源：内容相同的只留一份，但保留导入包里的 id，保证卡牌里的引用可解析
    local = {a["id"]: a for a in repo.list_assets()}
    sha_map: Dict[str, dict] = {}
    for aid in list(local):
        a = repo.get_asset(aid)
        p = config.ASSETS_DIR / a.rel_path
        if p.exists():
            sha_map[_sha1(p.read_bytes())] = a.model_dump()

    # 资源清单：assets.json 为主；旧包缺 `rel_path` 时按 AssetItem 规则推导，
    # 若整份清单都缺失，再用每个资源旁边的 `<文件名>.meta.json` 兜底补齐。
    pkg_assets = json.loads(files.get("assets/assets.json", b"[]") or b"[]")
    for key, blob in files.items():
        if not (key.startswith("assets/") and key.endswith(".meta.json")):
            continue
        try:
            meta = json.loads(blob)
        except (ValueError, TypeError):
            continue
        if not any(a.get("id") == meta.get("id") for a in pkg_assets):
            pkg_assets.append(meta)

    missing: List[str] = []
    for a in pkg_assets:
        aid = a.get("id")
        if not aid:
            continue
        rel = _rel_path_of(a)
        blob = files.get(f"assets/{rel}") if rel else None
        if blob is None:
            missing.append(aid)
            continue
        if aid in local:
            continue                       # 同 id 已存在，直接复用
        dup = sha_map.get(_sha1(blob))
        if dup:
            a = {**a, "rel_path": dup["rel_path"]}   # 内容相同 → 指向本地那份
        else:
            target = config.ASSETS_DIR / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(blob)
        clean = {k: v for k, v in a.items() if k not in ("rel_path", "relPath")}
        if not any(i.get("id") == aid for i in repo.read_json(repo.ASSETS_INDEX, [])):
            repo.add_asset(AssetItem(**clean))
        sha_map[_sha1(blob)] = a

    for key, blob in files.items():
        if key.startswith("jobs/"):
            target = dst / key
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(blob)

    repo.save_project(repo.Project(**pdata))
    return {
        **pdata,
        "cardCount": cards_n,
        "templateCount": templates_n,
        "missingAssets": missing,
    }
