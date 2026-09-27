"""布局参考图：把模板的分区画成一张**纯线框**示意图，喂给图生图当版面约束。

四条视觉语言规则（都是实测踩出来的，改动前先看 `prompt.py` 的说明）：
  1. **只描边、不填充** —— 一旦填色，模型会照抄填充（绿斜纹→画满插画；浅灰→涂成白板）；
  2. **不渲染任何文字** —— 标签会被模仿成内容，在成品上留下"卡名"这类痕迹；
  3. **不画出血框/裁切框** —— 同样会被当成设计元素模仿，成品上留一圈怪线；
     出血约束改由提示词文字承担（`prompt.bleed_note()`）；
  4. 文字/数值区用细实线，图片/图标区用虚线（语义上的"空位"由此传达，
     真正的区域说明走提示词文本）。

画布尺寸默认**含出血**（净尺寸 + 四周），区域坐标整体 +bleed 偏移。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, List, Optional, Sequence, Tuple

#: 区域表元素：(名称, kind, (x, y, w, h)【设计像素】)
Zone = Tuple[str, str, Tuple[float, float, float, float]]


def zones_from_template(tpl: Any, limit: int = 8) -> List[Zone]:
    """从模板字段生成区域表（跳过 `guide=True` 的隐形定位框，按自上而下排序）。"""
    fields = [f for f in (getattr(tpl, "fields", None) or []) if not getattr(f, "guide", False)]
    if not fields:
        fields = list(getattr(tpl, "fields", None) or [])
    fields.sort(key=lambda f: (f.rect[1], f.rect[0]))
    out: List[Zone] = []
    for f in fields[:limit]:
        out.append((f.label or f.key, f.kind,
                    tuple(float(v) for v in f.rect[:4])))       # type: ignore[arg-type]
    return out


def build_layout_ref(w: int, h: int, path: Path, zones: Sequence[Zone],
                     src_w: Optional[int] = None, src_h: Optional[int] = None,
                     labels: bool = False) -> Path:
    """画布局参考图。`src_w/src_h` 是区域坐标所在的坐标系（默认与 w/h 相同）。

    输出**不带透明通道**的 RGB PNG：万相明确不接受带 alpha 的图。
    """
    from PIL import Image, ImageDraw

    src_w = src_w or w
    src_h = src_h or h
    img = Image.new("RGB", (w, h), (222, 222, 222))
    d = ImageDraw.Draw(img, "RGBA")
    sx, sy = w / src_w, h / src_h

    for name, kind, (x, y, rw, rh) in zones:
        box = (x * sx, y * sy, (x + rw) * sx, (y + rh) * sy)
        x0, y0, x1, y1 = box
        if kind in ("image", "icon"):
            dash, gap, xx = 16, 10, x0
            while xx < x1:
                d.line([(xx, y0), (min(xx + dash, x1), y0)], fill=(120, 120, 120, 255), width=2)
                d.line([(xx, y1), (min(xx + dash, x1), y1)], fill=(120, 120, 120, 255), width=2)
                xx += dash + gap
            yy = y0
            while yy < y1:
                d.line([(x0, yy), (x0, min(yy + dash, y1))], fill=(120, 120, 120, 255), width=2)
                d.line([(x1, yy), (x1, min(yy + dash, y1))], fill=(120, 120, 120, 255), width=2)
                yy += dash + gap
        else:
            d.rectangle(box, outline=(96, 96, 96, 255), width=2)
        if labels:      # 调试用；生产务必关闭
            d.text((x0 + 8, y0 + 8), "留空" if kind in ("image", "icon") else name,
                   fill=(70, 70, 70, 255))

    # 注意：**不要画出血框/裁切框**（用户 2026-09-27 要求）。
    # 参考图上只保留各字段区域的"内部框线"，出边区靠提示词文字说明 ——
    # 画了框会被模型当成设计元素模仿出来，成品上就会留下一圈不明所以的线。
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
    return path


def ref_for_template(tpl: Any, path: Path, bleed: bool = True) -> Path:
    """按模板画布局参考图。

    默认**按含出血尺寸出图**：画布 = 净尺寸 + 四周出血，所有区域坐标整体偏移 `bleed`。
    这样 AI 收到的参考图与它该出的画布是同一尺寸，模型不需要做任何脑补换算。
    """
    c = getattr(tpl, "canvas", None)
    w, h = int(getattr(c, "w", 745)), int(getattr(c, "h", 1040))
    b = int(getattr(c, "bleed", 0) or 0) if bleed else 0
    zones = [(n, k, (x + b, y + b, rw, rh)) for n, k, (x, y, rw, rh) in zones_from_template(tpl)]
    return build_layout_ref(w + b * 2, h + b * 2, path, zones, src_w=w + b * 2, src_h=h + b * 2)
