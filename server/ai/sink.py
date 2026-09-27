"""结果落地（sink）：拿到 URL **立刻下载**并登记成内部 asset，附 AI 溯源。

为什么必须立刻下载（§6.7）：生成结果的 URL **只有 24 小时有效**，且是外链。
一旦把 URL 写进模板/卡牌，第二天就是一堆裂图。所以：
    URL → 下载字节 → 落 workspace/assets/ → 登记 assets.json（含 aiProvenance）
    → 对外只暴露内部 assetId。

去重：同一次生成里内容相同的图（罕见但可能）按 sha1 只存一份。
"""
from __future__ import annotations

import base64
import hashlib
import io
import time
from typing import Any, Dict, List, Optional

import httpx

from .. import config
from ..store import repo
from ..store.schema import AssetItem, BaseplateMeta, now_iso
from ..util import thumbs

DOWNLOAD_TIMEOUT = httpx.Timeout(120.0, connect=20.0)


def _sha1(b: bytes) -> str:
    return hashlib.sha1(b).hexdigest()


def _download(url: str, retries: int = 3) -> bytes:
    """下载结果图。实测偶发抖动，重试 3 次。"""
    last: Optional[Exception] = None
    for i in range(retries):
        try:
            if url.startswith("b64:"):
                return base64.b64decode(url[4:])
            with httpx.Client(timeout=DOWNLOAD_TIMEOUT, follow_redirects=True) as c:
                r = c.get(url)
                r.raise_for_status()
                return r.content
        except Exception as e:
            last = e
            time.sleep(1 + i)
    raise RuntimeError(f"下载失败：{last}")


def save_images(urls: List[str], kind: str = "image", name_prefix: str = "ai",
                provenance: Optional[Dict[str, Any]] = None,
                tags: Optional[List[str]] = None) -> List[AssetItem]:
    """把生成结果下载并登记成 asset。kind ∈ {baseplate, image, icon}。

    返回登记后的 AssetItem 列表（前端只拿 id，通过 /api/assets/{id}/file 取图）。
    """
    prov = dict(provenance or {})
    prov.setdefault("createdAt", now_iso())
    out: List[AssetItem] = []
    seen: Dict[str, str] = {}          # sha1 -> asset id（同批去重）

    for i, u in enumerate(urls, 1):
        raw = _download(u)
        h = _sha1(raw)
        if h in seen:
            a = repo.get_asset(seen[h])
            if a:
                out.append(a)
            continue

        a = AssetItem(type=kind if kind in ("baseplate", "icon") else "image",
                      name=f"{name_prefix}_{i}", ext=".png",
                      tags=list(tags or []),
                      aiProvenance=BaseplateMeta(
                          provider=prov.get("provider"), model=prov.get("model"),
                          prompt=prov.get("prompt"), negativePrompt=prov.get("negativePrompt"),
                          seed=prov.get("seed"), size=prov.get("size"),
                          refImageHash=prov.get("refImageHash"),
                          requestId=prov.get("requestId"), createdAt=prov.get("createdAt")))
        dest = config.ASSETS_DIR / a.rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(raw)
        a.size = len(raw)
        repo.add_asset(a)
        # 底板/卡图都是大图（817×1112 起步），顺手出一张缩略图给列表用
        thumbs.make_thumb(dest, config.ASSETS_DIR, a.id)
        seen[h] = a.id
        out.append(a)
    return out


def image_size(raw_or_path: Any) -> Optional[Dict[str, int]]:
    """读取图片实际像素尺寸（用于校验模型是否遵守了请求的 size）。"""
    try:
        from PIL import Image
        if isinstance(raw_or_path, (str, )) and not str(raw_or_path).startswith("b64:"):
            img = Image.open(raw_or_path)
        else:
            data = raw_or_path[4:] if str(raw_or_path).startswith("b64:") else raw_or_path
            img = Image.open(io.BytesIO(base64.b64decode(data)))
        return {"w": img.width, "h": img.height}
    except Exception:
        return None
