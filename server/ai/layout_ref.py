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

#: 送给 AI 的元素：名称 / kind / rect(设计像素) / 该字段有没有衬底
AiElement = Tuple[str, str, Tuple[float, float, float, float], bool]

#: 参考图与提示词**必须用同一个上限** —— 图里画了却没在提示词里点名的区域，
#: 模型会直接忽略（甚至抹掉）；这是 V3 那轮实测踩出来的。
ZONE_LIMIT = 8


def _v(obj: Any, key: str, default: Any = None) -> Any:
    """pydantic 对象与 dict 都能取（提示词那边习惯用 dict 访问）"""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _ai_ref(obj: Any, default: bool) -> bool:
    """元素级「是否进 AI 参考图」开关。None = 走 default（向后兼容）。"""
    v = _v(obj, "aiRef", None)
    return default if v is None else bool(v)


def _rect_of(obj: Any) -> Tuple[float, float, float, float]:
    r = _v(obj, "rect", None) or [0, 0, 0, 0]
    return tuple(float(v) for v in r[:4])       # type: ignore[return-value]


def ai_elements(tpl: Any, limit: int = ZONE_LIMIT) -> List[AiElement]:
    """给 AI 的图与提示词**共用的元素选择**（唯一出处）。

    规则：
      * 字段：`aiRef` 缺省 = 「不是隐形定位框就进」（与改造前一致）；全是定位框时兜底全进。
      * 图层：`aiRef` 缺省 = **不进**（边框/色块进了参考图会被模型模仿成装饰线条），
        用户显式打开才画 —— 用途是告诉模型"这里已有固定图形，别重复画"。
      * 底板：不走这里（它是参考图的底，不是描线区域）。
    """
    fields = list(_v(tpl, "fields", None) or [])
    live = [f for f in fields if _ai_ref(f, not _v(f, "guide", False))]
    if not live:
        live = fields                       # 兜底：全被排除时退回全部（老逻辑）
    live.sort(key=lambda f: (_rect_of(f)[1], _rect_of(f)[0]))

    out: List[AiElement] = []
    for f in live:
        bd = _v(f, "backdrop", None)
        out.append((_v(f, "label", "") or _v(f, "key", "") or "",
                    _v(f, "kind", "text") or "text",
                    _rect_of(f), bool(_v(bd, "enabled", False))))

    layers = [l for l in (_v(tpl, "layers", None) or [])
              if _ai_ref(l, False) and not _v(l, "guide", False)]
    layers.sort(key=lambda l: (_rect_of(l)[1], _rect_of(l)[0]))
    for l in layers:
        out.append((f"图层·{_v(l, 'name', '') or ''}", "layer", _rect_of(l), False))

    return out[:limit]


def zones_from_template(tpl: Any, limit: int = ZONE_LIMIT) -> List[Zone]:
    """从模板生成区域表（字段 + 显式打开的图层），按自上而下排序。"""
    return [(n, k, r) for n, k, r, _bd in ai_elements(tpl, limit)]


def _dashed_rect(d: Any, box: Sequence[float], color: tuple,
                 dash: int = 16, gap: int = 10, width: int = 2) -> None:
    """四边虚线的矩形（ImageDraw 没有虚线选项，只能自己画段）"""
    x0, y0, x1, y1 = box
    xx = x0
    while xx < x1:
        d.line([(xx, y0), (min(xx + dash, x1), y0)], fill=color, width=width)
        d.line([(xx, y1), (min(xx + dash, x1), y1)], fill=color, width=width)
        xx += dash + gap
    yy = y0
    while yy < y1:
        d.line([(x0, yy), (x0, min(yy + dash, y1))], fill=color, width=width)
        d.line([(x1, yy), (x1, min(yy + dash, y1))], fill=color, width=width)
        yy += dash + gap


def build_layout_ref(w: int, h: int, path: Path, zones: Sequence[Zone],
                     src_w: Optional[int] = None, src_h: Optional[int] = None,
                     labels: bool = False, base_image: Optional[Path] = None) -> Path:
    """画布局参考图。`src_w/src_h` 是区域坐标所在的坐标系（默认与 w/h 相同）。

    `base_image` = 把**现有底板**垫在底下当底（模板里打开「底板 → 进 AI 参考图」时）：
    适合"基于当前底板改良/局部重画"，此时线框换成浅色以便在深色画面上看得见。

    输出**不带透明通道**的 RGB PNG：万相明确不接受带 alpha 的图。
    """
    from PIL import Image, ImageDraw, ImageOps

    src_w = src_w or w
    src_h = src_h or h
    img = Image.new("RGB", (w, h), (222, 222, 222))
    if base_image is not None and Path(base_image).exists():
        try:
            with Image.open(base_image) as b:
                img = ImageOps.fit(b.convert("RGB"), (w, h), Image.LANCZOS)
        except Exception:
            img = Image.new("RGB", (w, h), (222, 222, 222))
    d = ImageDraw.Draw(img, "RGBA")
    sx, sy = w / src_w, h / src_h

    on_art = base_image is not None
    c_solid = (255, 255, 255, 235) if on_art else (96, 96, 96, 255)
    c_dash = (255, 255, 255, 200) if on_art else (120, 120, 120, 255)
    c_dot = (255, 240, 150, 235) if on_art else (170, 150, 60, 255)

    for name, kind, (x, y, rw, rh) in zones:
        box = (x * sx, y * sy, (x + rw) * sx, (y + rh) * sy)
        x0, y0, x1, y1 = box
        if kind == "layer":
            # 已有固定图形的区域：点线，与"空位"区分开
            _dashed_rect(d, box, c_dot, dash=4, gap=8)
        elif kind in ("image", "icon"):
            _dashed_rect(d, box, c_dash, dash=16, gap=10)
        else:
            d.rectangle(box, outline=c_solid, width=2)
        if labels:      # 调试用；生产务必关闭
            d.text((x0 + 8, y0 + 8), "留空" if kind in ("image", "icon") else name,
                   fill=(70, 70, 70, 255))

    # 注意：**不要画出血框/裁切框**（用户 2026-09-27 要求）。
    # 参考图上只保留各字段区域的"内部框线"，出边区靠提示词文字说明 ——
    # 画了框会被模型当成设计元素模仿出来，成品上就会留下一圈不明所以的线。
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
    return path


def ref_for_template(tpl: Any, path: Path, bleed: bool = True,
                     base_image: Optional[Path] = None) -> Path:
    """按模板画布局参考图。

    默认**按含出血尺寸出图**：画布 = 净尺寸 + 四周出血，所有区域坐标整体偏移 `bleed`。
    这样 AI 收到的参考图与它该出的画布是同一尺寸，模型不需要做任何脑补换算。
    """
    c = getattr(tpl, "canvas", None)
    w, h = int(getattr(c, "w", 745)), int(getattr(c, "h", 1040))
    b = int(getattr(c, "bleed", 0) or 0) if bleed else 0
    zones = [(n, k, (x + b, y + b, rw, rh)) for n, k, (x, y, rw, rh) in zones_from_template(tpl)]
    return build_layout_ref(w + b * 2, h + b * 2, path, zones, src_w=w + b * 2, src_h=h + b * 2,
                            base_image=base_image)
