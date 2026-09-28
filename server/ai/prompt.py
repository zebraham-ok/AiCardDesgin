"""提示词语料层：ProjectBrief + Template + Card → Prompt（计划 §6.11）。

本文件的规则**全部来自 2026-09-27 的实测**（`server/ai/spike_images.py`，
样图在 `workspace/spike/`）。五个变体的对比结论：

| 变体 | 版面遵守 | 费用区(右上小方块) | 主画面 | 边框 |
|---|---|---|---|---|
| V1 朴素（只说"生成卡牌背景板"） | ❌ 完全无视参考图，自造通用卡框 | ❌ | ❌ 空 | 自加 |
| V2 分区（方位+用途，含全部四区） | ✅ | ✅ | ✅ | 自加 |
| V3 强约束（用百分比描述，漏写费用区） | 🟡 | ❌ 被吞掉 | ✅ | 自加 |
| **V4 点名分区**（方位+用途，禁画框） | ✅ | ✅ | ✅ | 无 |
| **V5 V4 + 注入项目语料** | ✅ | ✅ | ✅ 且配色/题材精确命中 | 无 |

由此定下的硬规则（写死在下面的拼装函数里）：

1. **必须逐区点名**：没写到的区域模型不会从参考图"看出来"，会直接消失（V3 的教训）。
2. **用方位+用途描述，不要用百分比数字**（"顶部横向窄条带""右上角的独立小方块"）。
3. **必须显式禁止画框**（"不要画框、不要相框线"），否则模型会自加装饰边框；
   我们的模板通常自带边框图层，底板再加一圈就重了。
4. **图片位必须明确写"留空"** —— 不点名它就会自作主张（V1 留一片空、V4/V5 画满插画，
   两者都不是底板要的）。**底板只生成外壳**：边缘装饰 + 各分区底材质，
   卡图区是留给后续单卡配图的空坑。
5. **参考图只描边、不填充** —— 分区一旦填色，模型会照抄那个填充：
   绿色斜纹 → 它在图片区画满一张插画；浅灰 → 它把分区涂成白板。
   纯线稿（实线=文字区 / 虚线+「留空」=配图空位）下，模型才会把"底色"当成要替换的目标。
6. **别用"留白 / 素净 / 空"这类词** —— 会被理解成"涂白"，成品变成"深色框 + 几块白板"。
   正确写法是"**延续整体材质、只降低对比度和细节**"，同时把
   「白色面板 / 白色色块 / 灰白色块」写进负向词，并正向强调"材质与色调必须连续统一"。

> 第 4–6 条来自用户 2026-09-27 的设计澄清与随后三轮实测：底板的图片位本来就该是空的，
> 因为每张卡的配图是后面单独生成/上传的。底板若在图区画了东西，
> ① 白花一次生成费用；② 卡图有圆角、留白或 contain 时，底板花纹会从缝里露出来。

另外：语料块注入是有效的（V5 的 `#0b1a2b/#c9a227` 与"星际/舰队/遗迹"精确生效），
所以 ProjectBrief 的 `artStyle.palette / mood / keywords` 值得让用户填。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

# 元素选择与参考图共用（唯一出处）：图里画什么、提示词里就点名什么
from .layout_ref import ZONE_LIMIT, ai_elements

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
#: 固定负向词：无论项目怎么配都要带上
#: 「白色面板」这几条是实测加的：只要正向词里出现"留白/素净/空"，模型就会把分区
#: 涂成白色或灰色的空白面板，整张图变成"深色框 + 三块白板"，完全不像卡牌底板。
BASE_NEGATIVE = ["文字", "汉字", "字母", "数字", "符号", "水印", "签名", "logo",
                 "边框", "相框线", "粗重装饰边框", "文字块", "杂乱细节",
                 "白色面板", "白色色块", "灰白色块", "空白白板", "纯白方块",
                 "分割的白块", "贴纸感"]

#: 图片 / 图标区的处理：**留空**。
#:
#: 设计澄清（用户 2026-09-27）：底板只是"外壳"，图片位是**留给后续单卡配图的空位**，
#: 底板阶段绝不能往里画插画 —— 否则①白花钱生成会被覆盖的内容；②卡图有圆角/留白/
#: contain 时，底板的花纹会从缝里露出来，拼接感很脏。
#: 区域措辞的两条铁律（都是踩过的坑）：
#:  ① 不要用"留白/空/素净"这种词 —— 模型会理解成"涂白"；
#:  ② 要写"延续整体材质、只降对比度"，这样才既干净又不脱底。
_TEXT_SLOT = ("叠加文字区：与整体材质连续，只是把对比度和细节降到很低"
              "（同色系的平整材质），不要纯白色块，也不要灰色面板")
_EMPTY_SLOT = ("配图空位：此处后续会放置卡牌自己的配图，现在只需要延续整体材质、"
               "保持平坦无内容，不要画任何插画、图案或纹理，也不要纯白色块或灰色面板")

#: 各 kind 的区域用途描述
_KIND_PURPOSE = {
    "text": _TEXT_SLOT,
    "textarea": _TEXT_SLOT,
    "number": "数值区：与整体材质连续，局部平坦、明度略作区分即可放下一个数字，不要纯白色块",
    "enum": "标记区：与整体材质连续的小块平坦区域，不要纯白色块",
    "image": _EMPTY_SLOT,
    "icon": _EMPTY_SLOT,
    # 图层（用户在模板里显式打开「进 AI 参考图」的那些）：告诉模型这里有固有图形，
    # 免得它又在同一位置画一条装饰边框（模型天生爱加框，见 §6.10 硬规则 3）
    "layer": "既有装饰区：这里已由模板自带的固定图形占据，底板只需延续材质，"
             "不要在此处再画边框、色块或装饰线",
}


# ---------------------------------------------------------------------------
# 语料块（从 ProjectBrief 取词）
# ---------------------------------------------------------------------------
def brief_blocks(brief: Any) -> Dict[str, str]:
    """把 ProjectBrief 拆成 6 个语料块（§6.11 的「语料块」表）。

    空字段直接跳过 —— 缺料时只是少一块，不阻断生成。
    """
    b = brief or {}
    art = _g(b, "artStyle") or {}

    style = _g(art, "style") or ""
    details = _g(art, "details") or ""
    mood = _g(art, "mood") or []
    palette = [c for c in (_g(art, "palette") or []) if c]
    keywords = _g(b, "keywords") or []
    genre = _g(b, "genre") or []
    refs = _g(art, "references") or []
    synopsis = (_g(b, "synopsis") or "").strip()
    factions = _g(b, "factions") or []
    taboos = _g(b, "taboos") or []

    blocks: Dict[str, str] = {}
    if style or details:
        blocks["风格"] = "，".join(x for x in [style, details] if x)
    if mood:
        blocks["氛围"] = "、".join(mood)
    if palette:
        blocks["主色板"] = _palette_sentence(palette)
    kw = list(keywords) + [g for g in genre if g not in keywords]
    if kw:
        blocks["题材关键词"] = "、".join(kw[:12])
    if synopsis:
        blocks["世界观"] = synopsis[:200]
    if factions:
        blocks["派系"] = "；".join(
            "{}（{}）".format(_g(f, "name"), _g(f, "desc") or "无描述")
            + (f"，主色 {_g(f, 'color')}" if _g(f, "color") else "")
            for f in factions if _g(f, "name"))
    if refs:
        blocks["参考作品"] = "、".join(refs[:6])
    if taboos:
        blocks["禁忌"] = "、".join(taboos)
    return blocks


def _palette_sentence(palette: List[str]) -> str:
    """色板写成一句人话（模型对"作底/点缀"这类角色描述比裸 hex 更敏感）。"""
    roles = ["作底", "作中景", "收边点缀", "作高光", "作阴影", "作点缀"]
    parts = [f"{c} {roles[i] if i < len(roles) else '作辅助色'}" for i, c in enumerate(palette)]
    return "，".join(parts) + "；整体色彩协调，避免高饱和刺眼"


def blocks_to_text(blocks: Dict[str, str], with_world: bool = False) -> str:
    keys = ["风格", "氛围", "主色板", "题材关键词", "参考作品", "派系", "世界观"] \
        if with_world else ["风格", "氛围", "主色板", "题材关键词", "参考作品", "派系"]
    return "\n".join(f"[{k}] {blocks[k]}" for k in keys if k in blocks)


# ---------------------------------------------------------------------------
# 版面分区描述（由模板字段自动生成 —— §6.4.2 第 ② 步）
# ---------------------------------------------------------------------------
def _zone_label(rect: List[float], W: float, H: float) -> str:
    """按形状 + 位置给区域一个**方位化**的名字（实测：方位描述比百分比可靠）。

    判定顺序很重要：先认"右上角小方块"，再认"大块"，最后才是"窄条"。
    早期版本先判窄条带，把卡图区（625×430）也当成了"顶部横向窄条带"。
    """
    x, y, w, h = rect
    right = (x + w) / W
    top, bottom = y / H, (y + h) / H
    center = (top + bottom) / 2

    if w < W * 0.25 and right > 0.68 and h < H * 0.25:
        return "画面右上角的独立小方块"
    if w < W * 0.30 and top < 0.22:
        return "画面顶部左侧的小矩形"

    big = w > W * 0.50 and h > H * 0.18
    if big:
        if center < 0.35:
            return "画面上部的大矩形区域"
        if center < 0.70:
            return "画面中部的大矩形区域"
        return "画面下部的大矩形区域"

    strip = h < H * 0.15
    if strip:
        if center < 0.25:
            return "画面顶部的横向窄条带"
        if center > 0.78:
            return "画面底部的横向窄条带"
        return "画面中部的横向条带"
    if center > 0.72:
        return "画面底部的一块矩形区域"
    return "画面中部的一块矩形区域"


def describe_zones(tpl: Any, limit: int = ZONE_LIMIT) -> List[str]:
    """把「给 AI 的元素表」转成自然语言分区描述（自上而下、从左到右）。

    **元素选择与参考图共用 `layout_ref.ai_elements()`**：图里画了什么，这里就描述什么。
    以前两边各写一份、上限还不一样（图 8 / 文 6）—— 画了却没说到的区域，模型会忽略甚至抹掉。
    """
    W = float(_g(_g(tpl, "canvas") or {}, "w") or 745)
    H = float(_g(_g(tpl, "canvas") or {}, "h") or 1040)

    out: List[str] = []
    seen: Dict[str, int] = {}
    for name, kind, rect, has_backdrop in ai_elements(tpl, limit):
        label = _zone_label(list(rect), W, H)
        seen[label] = seen.get(label, 0) + 1
        if seen[label] > 1:
            label = f"{label}（第 {seen[label]} 个）"   # 避免多个同名区域让模型混乱
        label = label.replace("画面", "", 1)
        purpose = _KIND_PURPOSE.get(kind, _KIND_PURPOSE["text"])
        if has_backdrop:
            # 衬底是模板侧自己叠加的半透明面板 —— 提前告诉模型，底板别在这儿用力
            purpose += "（该区的半透明面板由模板叠加，底板保持平整、低对比即可）"
        out.append(f"{label}（{name}）：{purpose}")
    return out


def _zones_text(zones: List[str]) -> str:
    if not zones:
        return ""
    marks = "①②③④⑤⑥⑦⑧⑨"
    lines = []
    for i, z in enumerate(zones):
        lines.append(f"{marks[i] if i < len(marks) else '-'} {z}")
    return ("版面自上而下必须严格保留以下区域，位置、比例与参考图完全一致：\n"
            + "\n".join(lines))


# ---------------------------------------------------------------------------
# 三个用途的拼装
# ---------------------------------------------------------------------------
def build_baseplate_prompt(tpl: Any, brief: Any = None,
                           extra: str = "", subject: str = "") -> Tuple[str, str]:
    """底板生图（I2I，模板区域图 → 卡牌外壳）。返回 (prompt, negative_prompt)。

    **只生成外壳**：边缘装饰 + 各分区的底材质，图片位一律留空。
    需要"整卡直出概念稿"（把画面也画进去）时，走 `subject` 参数单独拼一段。
    """
    blocks = brief_blocks(brief)
    head = blocks_to_text(blocks)
    zones = _zones_text(describe_zones(tpl))
    has_slot = any("留空" in z for z in describe_zones(tpl))
    subject_line = f"主画面区请绘制：{subject}。" if subject else ""

    parts = [
        "生成一张竖版桌游卡牌背景板（这是卡牌模板的**外壳**，不是成品卡面），"
        "尺寸与参考图完全一致，严格保留参考图的版面结构。",
        bleed_note(tpl),
        head,
        "整体质感统一、色调沉稳；边缘只做轻微的材质加深过渡，"
        "不要画框、不要相框线、不要粗重的装饰边框。",
        # 材质连续是这张图成败的关键（否则会变成"深色框 + 几块白板"）
        "整张背景板的底色与材质必须连续统一：所有分区都延续同一套材质，"
        "只通过明度和细节量做区分；画面中不要出现白色、灰白色的空白面板或色块。",
        # 参考图上的框线只是"版面示意"，实测会被模型当成内容描出来
        "参考图中的灰色线框只是版面位置示意，**不要把它们画成任何线条、描边或边框**，"
        "分区之间请用材质的明暗与质感自然过渡来区分。",
        zones,
        # 图片位是留给后续配图的空坑，必须点名否则模型会自作主张填满
        ("参考图中用虚线框标出的区域是**留给卡牌配图的空位**：延续整体材质、保持平坦无内容，"
         "不要在其中生成任何插画、图案或纹理，也不要涂成白色或灰色面板。" if has_slot else ""),
        subject_line,
        extra,
        "画面中严禁出现任何文字、字母、数字、符号、水印、签名、徽标或装饰性字母；"
        "各区域边界横平竖直、与参考图一致。",
    ]
    prompt = "\n".join(p for p in parts if p)

    neg = list(BASE_NEGATIVE)
    for t in (blocks.get("禁忌") or "").split("、"):
        t = t.strip()
        if t:
            neg.append(t.replace("不要", "").strip() or t)
    return prompt, "，".join(dict.fromkeys(neg))


def build_cardart_prompt(card: Any, tpl: Any = None, brief: Any = None,
                         field_key: str = "", extra: str = "") -> Tuple[str, str]:
    """卡图生图（T2I，一张卡 → 卡图区插画）。

    卡面上已有的文字（卡名、描述、其它文本字段、标签）**全部**作为画面依据，
    这是让配图和卡面内容对得上的关键（用户 2026-09-27 的要求）。
    """
    blocks = brief_blocks(brief)
    name = _g(card, "name") or "未命名卡牌"
    tags = _g(card, "tags") or []
    values = _g(card, "fields") or {}

    # 收集卡面上所有非空文本值（跳过图片类字段本身）
    texts: List[str] = []
    for f in (_g(tpl, "fields") or []):
        if _g(f, "guide") or _g(f, "binding") == "fixed":
            continue
        if _g(f, "kind") not in ("text", "textarea", "enum"):
            continue
        v = values.get(_g(f, "key"))
        if v not in (None, ""):
            texts.append(f"{_g(f, 'label') or _g(f, 'key')}：{str(v)[:160]}")
    desc = "；".join(texts[:4])

    lines = [f"为桌游卡牌「{name}」绘制一张卡面插画，构图完整、主体突出、单一场景。"]
    if desc:
        lines.append(f"卡面文字信息（画面依据）：{desc}")
    if tags:
        lines.append(f"卡牌标签：{'、'.join(str(t) for t in tags[:6])}")
    # 派系：卡牌字段里若标了 faction，取该派系的主色
    faction_txt = _faction_hint(card, brief)
    if faction_txt:
        lines.append(faction_txt)
    head = blocks_to_text(blocks)
    if head:
        lines.append(head)
    lines.append("不要出现任何文字、字母、数字、水印、签名或边框。")
    if extra:
        lines.append(extra)

    neg = list(BASE_NEGATIVE)
    for t in (blocks.get("禁忌") or "").split("、"):
        t = t.strip()
        if t:
            neg.append(t.replace("不要", "").strip() or t)
    return "\n".join(lines), "，".join(dict.fromkeys(neg))


def _faction_hint(card: Any, brief: Any) -> str:
    """卡牌上标了派系时，用它换出「主导色 + 气质」这句提示。"""
    factions = _g(brief or {}, "factions") or []
    if not factions:
        return ""
    vals = [str(v) for v in (_g(card, "fields") or {}).values()]
    tags = [str(t) for t in (_g(card, "tags") or [])]
    for f in factions:
        nm = _g(f, "name")
        if nm and (nm in vals or nm in tags or nm in (_g(card, "name") or "")):
            return (f"该卡属于派系「{nm}」：{_g(f, 'desc') or ''}，"
                    f"请以 {_g(f, 'color')} 为主导色。")
    return ""


def build_text_system_prompt(tpl: Any, brief: Any, count: int = 5) -> str:
    """文生文的 system：世界观 + 风格 + 关键词 + 由模板字段 schema 生成的输出结构。"""
    b = brief_blocks(brief)
    fields = []
    for f in (_g(tpl, "fields") or []):
        if _g(f, "binding") == "fixed" or _g(f, "guide"):
            continue
        c = _g(f, "constraint") or {}
        spec = f'- "{_g(f, "key")}"（{_g(f, "label")}，{_g(f, "kind")}'
        if _g(c, "type") in ("int", "float"):
            spec += f'，范围 {_g(c, "min")}~{_g(c, "max")}'
        if _g(c, "options"):
            spec += f'，只能是 {"/".join(_g(c, "options"))} 之一'
        if _g(c, "maxLen"):
            spec += f'，不超过 {_g(c, "maxLen")} 字'
        fields.append(spec + "）")

    lines = [
        "你是桌游卡牌文案设计师，为一个已定型的游戏批量生成卡牌数据。",
        (f"游戏名：{_g(brief or {}, 'title')}" if _g(brief or {}, "title") else ""),
        (f"一句话卖点：{_g(brief or {}, 'oneLiner')}" if _g(brief or {}, "oneLiner") else ""),
        (f"世界观：{b['世界观']}" if "世界观" in b else ""),
        (f"风格：{b['风格']}" if "风格" in b else ""),
        (f"氛围：{b['氛围']}" if "氛围" in b else ""),
        (f"关键词：{b['题材关键词']}" if "题材关键词" in b else ""),
        (f"派系：{b['派系']}" if "派系" in b else ""),
        "字段定义：",
        *fields,
        f"请生成 {count} 张卡的 JSON，结构为 "
        '{"cards":[{"name":"...","tags":["..."], ...其余字段按上面的 key]}}。',
        "数值必须落在给定范围内；不要输出任何解释性文字，只输出 JSON。",
        "保持术语与命名风格统一，卡名简洁有力、彼此不重复。",
    ]
    return "\n".join(x for x in lines if x)


# ---------------------------------------------------------------------------
# 尺寸
# ---------------------------------------------------------------------------
#: 模型对过小的图不友好（万相要求总像素 ≥ 768×768，千问虽宽松但小图质量差）。
#: 卡图区可能只有 400×300，所以按比例放大到安全尺寸，**比例保持不变**。
MIN_SIDE = 512
MIN_AREA = 512 * 512


def fit_ai_size(w: float, h: float, min_side: int = MIN_SIDE,
                min_area: int = MIN_AREA) -> tuple[int, int]:
    """把目标尺寸按比例放大到模型可接受的下限（比例不变）。"""
    w, h = max(1.0, float(w)), max(1.0, float(h))
    scale = 1.0
    if min(w, h) < min_side:
        scale = min_side / min(w, h)
    if w * h * scale * scale < min_area:
        scale = (min_area / (w * h)) ** 0.5
    return int(round(w * scale)), int(round(h * scale))


def bleed_px(tpl: Any) -> int:
    """出血像素（模板 canvas.bleed，默认 3mm@dpi）。"""
    return int(_g(_g(tpl, "canvas") or {}, "bleed") or 0)


def baseplate_size(tpl: Any, bleed: bool = True) -> str:
    """底板尺寸。

    **默认含出血**（用户 2026-09-27 定）：底板按 `净尺寸 + 四周出血` 生成，
    这样 trim 导出时从中间裁、bleed 导出时整张铺满，两种模式都像素级 1:1，
    不需要任何缩放；若只生成净尺寸，含出血导出就得把图放大 ~9.7% 去填，
    贴边的装饰会被裁掉、所见与所得不一致。

    面积从 775k 变成 908k，仍远低于 2.25M 的 1K/2K 分档线，**计价档位不变**。
    """
    c = _g(tpl, "canvas") or {}
    w, h = int(_g(c, "w") or 745), int(_g(c, "h") or 1040)
    b = bleed_px(tpl) if bleed else 0
    return f"{w + b * 2}x{h + b * 2}"


def bleed_note(tpl: Any) -> str:
    """把"外围会被裁掉"写进提示词 —— 参考图上**不画**出血线（用户要求），
    所以这条约束只能由文字承担。"""
    c = _g(tpl, "canvas") or {}
    w, h = float(_g(c, "w") or 745), float(_g(c, "h") or 1040)
    b = bleed_px(tpl)
    if not b:
        return ""
    pct_w = b / (w + 2 * b) * 100
    pct_h = b / (h + 2 * b) * 100
    return (f"画面四周各留出 {b}px（约占宽 {pct_w:.1f}%、高 {pct_h:.1f}%）作为**出血区**，"
            "这部分印刷后会被裁掉：材质与背景必须自然延伸过去（不要留白边、不要画边框线），"
            "但**任何重要的图案、装饰、元素都不要放进出边区**。")


def cardart_size(tpl: Any, field_key: str = "") -> str:
    """卡图尺寸 = **该图片字段的区域大小**（过小时按比例放大到安全下限）。"""
    f = _find_field(tpl, field_key, kinds=("image", "icon"))
    if not f:
        c = _g(tpl, "canvas") or {}
        return baseplate_size(tpl)
    rect = list(_g(f, "rect") or [625, 430, 625, 430])
    w, h = fit_ai_size(rect[2], rect[3])
    return f"{w}x{h}"


def _find_field(tpl: Any, key: str = "", kinds: tuple = ()) -> Any:
    for f in (_g(tpl, "fields") or []):
        if _g(f, "guide"):
            continue
        if key and _g(f, "key") != key:
            continue
        if kinds and _g(f, "kind") not in kinds:
            continue
        return f
    return None


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------
def _g(obj: Any, key: str) -> Any:
    """模板/简报里有些节点是 dict、有些是 Pydantic 模型，统一取值。"""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def preview(pid_brief: Any, tpl: Any, card: Any = None,
            kind: str = "baseplate", subject: str = "", extra: str = "",
            field_key: str = "") -> Dict[str, Any]:
    """给前端「提示词预览」用：返回拼好的 prompt / negative / 目标尺寸（不调 API、不扣费）。"""
    if kind == "cardart":
        p, n = build_cardart_prompt(card or {}, tpl, pid_brief,
                                    field_key=field_key, extra=extra)
        size = cardart_size(tpl, field_key)
    elif kind == "text":
        p, n = build_text_system_prompt(tpl, pid_brief), ""
        size = ""
    else:
        p, n = build_baseplate_prompt(tpl, pid_brief, extra=extra, subject=subject)
        size = baseplate_size(tpl)
    return {"prompt": p, "negative_prompt": n, "size": size,
            "zones": describe_zones(tpl) if kind == "baseplate" else [],
            # 是否会在参考图里垫上现有底板（模板里「底板 → 进 AI 参考图」开关）
            "refBase": bool(kind == "baseplate" and _g(_g(tpl, "background") or {}, "aiRef")),
            "blocks": brief_blocks(pid_brief)}
