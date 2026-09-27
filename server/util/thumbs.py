"""缩略图：资源列表 / 资源选择器不该拉原图。

底板是 817×1112 的 PNG（一张 1–2 MB），列表里几十张就是几十 MB；
这里在上传或 AI 落盘时顺手生成一张 480px 的 JPEG 缩略图，
原图仍然完整保留（导出、渲染都用原图）。
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

MAX_SIDE = 480


def thumb_dir(assets_dir: Path) -> Path:
    return assets_dir / "thumbs"


def thumb_path(assets_dir: Path, asset_id: str) -> Path:
    return thumb_dir(assets_dir) / f"{asset_id}.jpg"


def make_thumb(src: Path, assets_dir: Path, asset_id: str,
               max_side: int = MAX_SIDE) -> Optional[Path]:
    """为一图片生成 JPEG 缩略图。

    失败一律返回 None —— 缩略图是优化项，**不能因为它把上传或 AI 落盘搞失败**
    （SVG 不能直接喂 Pillow，就是这种情况）。
    """
    try:
        from PIL import Image

        with Image.open(src) as im:
            im.load()
            if im.mode in ("RGBA", "LA", "P"):
                rgba = im.convert("RGBA")
                bg = Image.new("RGB", rgba.size, (255, 255, 255))
                bg.paste(rgba, mask=rgba.split()[-1])   # 透明底铺白，JPEG 不支持 alpha
                im = bg
            else:
                im = im.convert("RGB")
            im.thumbnail((max_side, max_side), Image.LANCZOS)
            out = thumb_path(assets_dir, asset_id)
            out.parent.mkdir(parents=True, exist_ok=True)
            im.save(out, "JPEG", quality=82, optimize=True)
            return out
    except Exception:
        return None
