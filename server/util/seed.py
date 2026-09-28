"""首次启动的种子数据：6 个内置 icon 子库 + 一个示例项目。

icon 一律用 SVG，统一 `stroke=currentColor`，因此可在编辑器里换色。
"""
from __future__ import annotations

from .. import config
from ..store import repo
from ..store.schema import (AssetItem, Card, Constraint, FieldDef, Layer,
                            Project, StyleSpec, Template)

# (文件名, 中文名, 标签, svg body)
ICON_SPEC = {
    "elements": [
        ("fire", "火", ["fire", "火焰"],
         '<path d="M12 3c2.5 3.5 4.5 5.5 4.5 8.5a4.5 4.5 0 1 1-9 0C7.5 9 9.5 6.5 12 3Z"/>'
         '<path d="M12 16.5a1.6 1.6 0 0 1-1.6-1.6c0-1 .6-1.9 1.6-3.2.9 1.1 1.6 2 1.6 3.2a1.6 1.6 0 0 1-1.6 1.6Z"/>'),
        ("water", "水", ["water", "水滴"],
         '<path d="M12 3s6 6.6 6 10.6A6 6 0 0 1 6 13.6C6 9.6 12 3 12 3Z"/>'),
        ("wind", "风", ["wind", "空气"],
         '<path d="M3 8h10a3 3 0 1 0-3-3"/><path d="M3 12h14a3 3 0 1 1-3 3"/><path d="M3 16h8"/>'),
        ("earth", "土", ["earth", "大地"],
         '<path d="M3 18l6-9 4 5 2.5-3.5L21 18H3Z"/>'),
        ("light", "光", ["light", "神圣"],
         '<circle cx="12" cy="12" r="4"/>'
         '<path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5 19 19M19 5l-1.5 1.5M6.5 17.5 5 19"/>'),
        ("dark", "暗", ["dark", "暗影"],
         '<path d="M20.5 14.5A8.5 8.5 0 1 1 11 3.2 7 7 0 0 0 20.5 14.5Z"/>'),
        ("thunder", "雷", ["thunder", "闪电"],
         '<path d="M13 2 5 13h5l-1 9 8-11h-5l1-9Z"/>'),
        ("ice", "冰", ["ice", "冰霜"],
         '<path d="M12 3v18M4.2 7.5l15.6 9M19.8 7.5l-15.6 9"/>'
         '<path d="M12 6l-2-2M12 6l2-2M12 18l-2 2M12 18l2 2"/>'),
    ],
    "resources": [
        ("coin", "金币", ["coin", "金钱"],
         '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3.2"/>'),
        ("wood", "木材", ["wood", "木"],
         '<rect x="4" y="7" width="11" height="10" rx="4"/><path d="M15 7v10"/>'
         '<rect x="18" y="9" width="3" height="6" rx="1.5"/>'),
        ("ore", "矿石", ["ore", "矿"],
         '<circle cx="8" cy="14" r="3.2"/><circle cx="15.5" cy="15" r="2.4"/><circle cx="13" cy="8" r="3"/>'),
        ("grain", "粮食", ["grain", "食物"],
         '<path d="M12 21V9"/><path d="M12 9c0-3 2-5.2 5-5.2 0 3-2 5.2-5 5.2Z"/>'
         '<path d="M12 13c0-3-2-5-5-5 0 3 2 5 5 5Z"/>'
         '<path d="M12 17c0-2.4 2-4 4-4 0 2.4-2 4-4 4Z"/>'),
        ("crystal", "水晶", ["crystal", "宝石"],
         '<path d="M12 3l6 6-6 12-6-12 6-6Z"/><path d="M6 9h12"/>'),
        ("energy", "能量", ["energy", "电力"],
         '<rect x="3" y="7" width="13" height="10" rx="2"/><path d="M19 10v4"/><path d="M16 8v8"/>'),
    ],
    "status": [
        ("poison", "中毒", ["poison", "毒性"],
         '<circle cx="12" cy="12" r="8"/><path d="M9 14.5h6"/>'
         '<circle cx="9.6" cy="9.6" r=".9" fill="currentColor" stroke="none"/>'
         '<circle cx="14.4" cy="9.6" r=".9" fill="currentColor" stroke="none"/>'),
        ("dizzy", "眩晕", ["dizzy", "混乱"],
         '<circle cx="12" cy="12" r="9"/><path d="M8 9.5l8 5M16 9.5l-8 5"/>'),
        ("shield", "护盾", ["shield", "防御"],
         '<path d="M12 3l8 3v6c0 5-4 8-8 9-4-1-8-4-8-9V6l8-3Z"/>'),
        ("haste", "加速", ["haste", "迅捷"],
         '<path d="M6 6l6 6-6 6M14 6l6 6-6 6"/>'),
        ("slow", "减速", ["slow", "迟缓"],
         '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3.2 2.2"/>'),
        ("sleep", "睡眠", ["sleep", "沉睡"],
         '<path d="M3 9h8l-8 8h8"/><path d="M13 6h5l-5 5h5"/>'),
        ("burn", "灼烧", ["burn", "燃烧"],
         '<circle cx="12" cy="12" r="8.5"/>'
         '<path d="M12 6.5c1.4 1.9 2.4 3 2.4 4.5a2.4 2.4 0 1 1-4.8 0c0-1.5 1-2.6 2.4-4.5Z"/>'),
        ("silence", "沉默", ["silence", "禁言"],
         '<circle cx="12" cy="12" r="8.5"/><path d="M6 18 18 6"/>'),
    ],
    "classes": [
        ("warrior", "战士", ["warrior", "近战"],
         '<path d="M17 3h4v4l-8 8-4-4 8-8Z"/><path d="M6.5 13.5l4 4"/><path d="M5.5 16.5 3.5 20.5"/>'),
        ("mage", "法师", ["mage", "法术"],
         '<path d="M5 21l8-14"/>'
         '<path d="M14 5l1.4-2.8L18.2 5l2.8 2.8L18.2 10.6 15.4 7.8 12.6 10.6 14 5Z"/>'),
        ("priest", "牧师", ["priest", "治疗"],
         '<path d="M12 4v16"/><path d="M5.5 10h13"/>'),
        ("ranger", "游侠", ["ranger", "远程"],
         '<path d="M5 3a14 14 0 0 1 16 16"/><path d="M5 3l15.5 15.5"/><path d="M11 7.5l4.5 4.5"/>'),
        ("rogue", "盗贼", ["rogue", "潜行"],
         '<path d="M14 3l7 7-8.5 8.5-6 1 1-6L14 3Z"/><path d="M4 21l3.5-3.5"/>'),
        ("artisan", "工匠", ["artisan", "锻造"],
         '<path d="M3 21l6-6"/><path d="M9 15l-4-4 6.5-6.5 4 4L9 15Z"/><path d="M13 3.5l7.5 7.5-3.5 3.5-4-4 0-7Z"/>'),
    ],
    "arrows": [
        ("arrow-right", "向右", ["arrow", "右"],
         '<path d="M4 12h15"/><path d="M13 6l6 6-6 6"/>'),
        ("arrow-up", "向上", ["arrow", "上"],
         '<path d="M12 20V5"/><path d="M6 11l6-6 6 6"/>'),
        ("arrow-down", "向下", ["arrow", "下"],
         '<path d="M12 4v15"/><path d="M6 13l6 6 6-6"/>'),
        ("arrow-curve", "转折", ["arrow", "弯折"],
         '<path d="M4 20V10a6 6 0 0 1 6-6h8"/><path d="M14 8l4-4 4 4"/>'),
        ("arrow-bidirectional", "双向", ["arrow", "双向"],
         '<path d="M7 8l-4 4 4 4"/><path d="M17 8l4 4-4 4"/><path d="M4 12h16"/>'),
        ("arrow-cycle", "循环", ["cycle", "循环"],
         '<path d="M20 12a8 8 0 1 1-2.4-5.7"/><path d="M20 4v4h-4"/>'),
        ("target", "指向", ["target", "目标"],
         '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3"/>'
         '<path d="M12 2v2.5M12 19.5V22M2 12h2.5M19.5 12H22"/>'),
    ],
    "numeric": [
        ("d20", "D20", ["dice", "d20"],
         '<path d="M12 3l9 5v8l-9 5-9-5V8l9-5Z"/><path d="M3 8l9 5 9-5"/><path d="M12 13v8"/><path d="M12 13 3 8M12 13l9-5"/>'),
        ("counter", "计数", ["counter", "标记"],
         '<rect x="4" y="4" width="16" height="16" rx="3"/><path d="M9 12h6"/><path d="M12 9v6"/>'),
    ],
}

_DICE_PIPS = {
    1: [(12, 12)],
    2: [(8, 8), (16, 16)],
    3: [(8, 8), (12, 12), (16, 16)],
    4: [(8, 8), (16, 8), (8, 16), (16, 16)],
    5: [(8, 8), (16, 8), (12, 12), (8, 16), (16, 16)],
    6: [(8, 7), (16, 7), (8, 12), (16, 12), (8, 17), (16, 17)],
}


def _dice_svg(n: int) -> str:
    pips = "".join(
        f'<circle cx="{x}" cy="{y}" r="1.6" fill="currentColor" stroke="none"/>'
        for x, y in _DICE_PIPS[n])
    return f'<rect x="3.5" y="3.5" width="17" height="17" rx="4"/>{pips}'


SVG_WRAP = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
            'fill="none" stroke="currentColor" stroke-width="1.7" '
            'stroke-linecap="round" stroke-linejoin="round">{body}</svg>')


def seed_icons() -> int:
    """写入 6 个内置 icon 子库。已存在则跳过。"""
    existing = {(a.get("library"), a.get("name"))
                for a in repo.list_assets(type_="icon")}
    count = 0
    for lib, icons in ICON_SPEC.items():
        d = config.ASSETS_DIR / "icons" / lib
        d.mkdir(parents=True, exist_ok=True)
        items = list(icons)
        if lib == "numeric":
            for n in range(1, 7):
                items.append((f"dice-{n}", f"骰面{n}", ["dice", "骰子"],
                              _dice_svg(n)))
        for fname, cn, tags, body in items:
            if (lib, cn) in existing:
                continue
            a = AssetItem(type="icon", name=cn, library=lib,
                          tags=tags + [fname], ext=".svg", colorable=True)
            svg = SVG_WRAP.format(body=body)
            p = config.ASSETS_DIR / a.rel_path
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(svg, encoding="utf-8")
            a.size = len(svg.encode("utf-8"))
            repo.add_asset(a)
            count += 1
    return count


def seed_demo_project() -> None:
    """示例项目：一个法术卡模板 + 3 张卡。"""
    if repo.list_projects():
        return
    p = Project(name="示例：法术卡", description="用于快速了解工作流的示例项目",
                tags=["示例"])
    repo.save_project(p)

    name_style = StyleSpec(fontSize=44, weight=700, align="left",
                           valign="middle", autoShrink=True, minFontSize=24)
    cost_style = StyleSpec(fontSize=56, weight=700, align="center",
                           valign="middle", color="#ffffff")
    desc_style = StyleSpec(fontSize=28, align="left", valign="top",
                           autoShrink=True, minFontSize=20)

    t = Template(
        projectId=p.id, name="法术卡",
        description="63×88mm 标准卡牌",
        layers=[
            Layer(name="卡框", type="rect", rect=[14, 14, 717, 1012],
                  fill="#f3e6cf", stroke="#8b5a2b", strokeWidth=6, radius=24),
            Layer(name="卡图区底", type="rect", rect=[60, 170, 625, 420],
                  fill="#d9c7a8", radius=8),
            Layer(name="描述区底", type="rect", rect=[60, 620, 625, 300],
                  fill="#efe3cd", radius=8),
        ],
        fields=[
            FieldDef(key="name", label="卡名", kind="text",
                     rect=[60, 60, 560, 80], style=name_style, order=0,
                     constraint=Constraint(type="string", maxLen=20,
                                           default="未命名")),
            FieldDef(key="cost", label="费用", kind="number",
                     rect=[640, 55, 90, 90], style=cost_style, order=1,
                     constraint=Constraint(type="int", min=0, max=10,
                                           default=1)),
            FieldDef(key="art", label="卡图", kind="image",
                     rect=[60, 170, 625, 420], order=2),
            FieldDef(key="element", label="元素", kind="icon",
                     rect=[62, 596, 36, 36], order=3,
                     iconLibrary="elements"),
            FieldDef(key="desc", label="描述", kind="text", multiline=True,
                     rect=[60, 620, 625, 300], style=desc_style, order=4,
                     constraint=Constraint(type="string", maxLen=200,
                                           default="")),
            FieldDef(key="copyright", label="版权行", kind="text",
                     binding="fixed", value="© 2026 MyGame",
                     rect=[60, 960, 400, 30], order=5,
                     style=StyleSpec(fontSize=18, color="#8b5a2b")),
        ],
        background={"color": "#f3e6cf"},
    )
    repo.save_template(t)

    demo = [
        ("火球术", 3, "造成 3 点火焰伤害。若目标处于灼烧状态，伤害 +2。", ["伤害", "火"]),
        ("寒冰护盾", 2, "获得 5 点护盾，持续到下个回合开始。", ["防御", "冰"]),
        ("雷霆一击", 6, "对全体敌人造成 4 点雷电伤害，并使其眩晕 1 回合。", ["伤害", "雷"]),
    ]
    for n, cost, desc, tags in demo:
        repo.save_card(Card(projectId=p.id, templateId=t.id, name=n, tags=tags,
                            fields={"name": n, "cost": cost, "art": None,
                                    "element": None, "desc": desc}))
