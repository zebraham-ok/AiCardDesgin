"""唯一 schema 定义源（Pydantic v2）。

约定：
  * 模板/卡牌/项目都持久化成我们自己的 schema，**不持久化 Fabric JSON**
  * 坐标一律用「设计像素」（与 canvas.w/h 同坐标系），不存百分比
  * 图片资源一律用 asset:// 内部 URI，绝不存绝对路径
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


def new_id(prefix: str) -> str:
    import uuid
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


# --------------------------------------------------------------------------
# 画布 / 图层 / 字段
# --------------------------------------------------------------------------
class CanvasSpec(BaseModel):
    w: int = 745
    h: int = 1040
    dpi: int = 300
    bleed: int = 36
    w_mm: float = 63
    h_mm: float = 88


class StyleSpec(BaseModel):
    """文本样式。autoShrink 开启后按 min/max 字号二分缩放。"""
    fontFamily: str = "sans-serif"
    fontSize: int = 32
    weight: int = 400
    color: str = "#1a1a1a"
    align: Literal["left", "center", "right"] = "left"
    valign: Literal["top", "middle", "bottom"] = "top"
    vertical: bool = False            # 竖排（竖右）
    lineHeight: float = 1.2
    letterSpacing: float = 0
    autoShrink: bool = True
    minFontSize: int = 16
    stroke: Optional[str] = None
    strokeWidth: int = 0
    shadow: bool = False


class Layer(BaseModel):
    """模板里固定不变的图形底衬（rect / image / text / line）。"""
    id: str = Field(default_factory=lambda: new_id("ly"))
    type: Literal["rect", "image", "text"] = "rect"
    name: str = "图层"
    locked: bool = True
    visible: bool = True
    # 渲染顺序（小 → 先画 → 在下层）。None = 老数据未迁移，渲染器按数组下标补。
    # 字段用 FieldDef.order 当同一个 z，两者一起排序绘制。
    z: Optional[int] = None
    # 是否画进「给 AI 的布局参考图」（以及提示词里点名）。
    # None = 默认 **False**：图层多是边框/色块，进了参考图会被模型模仿成装饰线条。
    aiRef: Optional[bool] = None
    rect: List[float] = [0, 0, 100, 100]   # [x, y, w, h]
    fill: Optional[str] = None
    stroke: Optional[str] = None
    strokeWidth: int = 0
    radius: int = 0
    opacity: float = 1.0
    assetId: Optional[str] = None           # type=image 时
    text: Optional[str] = None              # type=text 时
    style: Optional[StyleSpec] = None
    # 隐形定位框：不参与卡牌渲染，只在模板编辑器里以虚线占位显示。
    # 用于 AI 底板生成流程（先画区域框 → 出底板 → 区域框转为定位框）。
    guide: bool = False


class Constraint(BaseModel):
    type: Literal["int", "float", "string", "enum", "bool"] = "string"
    min: Optional[float] = None
    max: Optional[float] = None
    maxLen: Optional[int] = None
    options: List[str] = []
    default: Any = None


class Backdrop(BaseModel):
    """字段衬底：跟着字段走的那块底板（描述区面板、卡图外框…）。

    刻意**不做成独立图层对象**，而是由「字段 rect + pad」现算出来的矩形：
      * 移动/缩放字段时衬底自动跟随 —— 不需要任何同步代码，也不可能被拖歪；
      * 渲染时永远紧贴字段的前一层或后一层，不参与全局 z 排序，不会出现
        "面板和文字各自跑" 的状态（这正是手动画个矩形当面板的痛点）。
    需要横跨多个字段的装饰（丝带、角花、水印）仍用独立图层。
    """
    enabled: bool = False
    # 内外扩边距 [上, 右, 下, 左]
    pad: List[float] = [8, 10, 8, 10]
    # 默认半透明白：压暗底板的材质以保证文字可读（透明度靠 opacity 调，
    # 不靠颜色的 alpha —— 两个 alpha 相乘会让人算不明白）
    fill: Optional[str] = "#ffffff"
    stroke: Optional[str] = None
    strokeWidth: int = 0
    radius: int = 8
    opacity: float = 0.8
    placement: Literal["behind", "front"] = "behind"


class FieldDef(BaseModel):
    """字段 = 可随卡牌变化的东西。binding 决定卡牌侧能否编辑。"""
    id: str = Field(default_factory=lambda: new_id("fd"))
    key: str                                # 唯一 key，导入映射靠它
    label: str
    backdrop: Optional[Backdrop] = None      # 可选衬底（见 Backdrop）
    # 是否画进「给 AI 的布局参考图」+ 提示词点名。
    # None = 默认「隐形定位框不进、普通字段进」（= 改造前的行为）
    aiRef: Optional[bool] = None
    # `"textarea"` 是**历史别名**，等价于 `kind="text" + multiline=True`：
    # 渲染/统计/AI 侧两者从来没有区别（同一套 Textbox + 自动换行），
    # 唯一差异只是卡牌页给单行输入框还是多行输入框 —— 所以改用 `multiline` 表达，
    # 编辑器里也不再暴露 textarea。保留这个别名只为老模板/老项目包不报错。
    kind: Literal["text", "textarea", "number", "enum", "image", "icon"] = "text"
    multiline: Optional[bool] = None      # None = 由 kind 推断（textarea → True）
    binding: Literal["editable", "fixed"] = "editable"
    rect: List[float] = [0, 0, 100, 40]
    style: StyleSpec = Field(default_factory=StyleSpec)
    constraint: Constraint = Field(default_factory=Constraint)
    fit: Literal["cover", "contain"] = "cover"
    radius: int = 0
    value: Any = None                       # binding=fixed 时的固定值
    iconLibrary: Optional[str] = None       # kind=icon 时限定的子库
    order: int = 0
    # 隐形定位框：卡牌与导出都不渲染，只在模板编辑器里显示虚线占位（AI 底板流程用）
    guide: bool = False


class BaseplateMeta(BaseModel):
    """底板 AI 生成溯源（M4 使用；M0-M3 阶段可为空）。"""
    provider: Optional[str] = None
    model: Optional[str] = None
    prompt: Optional[str] = None
    negativePrompt: Optional[str] = None
    seed: Optional[int] = None
    size: Optional[str] = None
    refImageHash: Optional[str] = None
    requestId: Optional[str] = None
    createdAt: Optional[str] = None


class Template(BaseModel):
    id: str = Field(default_factory=lambda: new_id("tpl"))
    projectId: str = ""
    name: str = "新模板"
    description: str = ""
    version: int = 1
    canvas: CanvasSpec = Field(default_factory=CanvasSpec)
    background: Dict[str, Any] = {}         # {assetId, fit, color}
    layers: List[Layer] = []
    fields: List[FieldDef] = []
    baseplate: Optional[BaseplateMeta] = None
    createdAt: str = Field(default_factory=now_iso)
    updatedAt: str = Field(default_factory=now_iso)


class Card(BaseModel):
    id: str = Field(default_factory=lambda: new_id("card"))
    projectId: str = ""
    templateId: str = ""
    name: str = "新卡牌"
    fields: Dict[str, Any] = {}
    overrides: Dict[str, Any] = {}
    tags: List[str] = []
    version: int = 1
    createdAt: str = Field(default_factory=now_iso)
    updatedAt: str = Field(default_factory=now_iso)


class Faction(BaseModel):
    """派系 / 阵营：生图时用来做同系列卡图的色彩与气质抓手。"""
    name: str = ""
    desc: str = ""
    color: str = "#8a8f98"          # 代表色（hex），生图时作为主色提示


class ArtStyle(BaseModel):
    """整体美术风格。AI 提示词的「风格块 / 氛围块 / 配色块」就取自这里。"""
    style: str = ""                 # 主风格，如「厚涂数字绘画」
    palette: List[str] = []         # 主色板 3-6 个 hex
    mood: List[str] = []            # 氛围词，如 ["史诗", "冷峻"]
    references: List[str] = []      # 参考作品，如 ["《沙丘》电影美术"]
    details: str = ""               # 细节补充（自由文本，直接进提示词）


class ProjectBrief(BaseModel):
    """创作简报（§4.4）：UI 表单 + AI 提示词语料层 + 项目包内容的三方共同数据源。

    全部字段可选；缺省时 AI 侧只是少几个语料块，不报错。
    """
    title: str = ""
    subtitle: str = ""
    oneLiner: str = ""              # 一句话卖点（首页卡片也用它）
    synopsis: str = ""              # 简介 / 世界观（≤200 字）
    players: str = ""
    playTime: str = ""
    age: str = ""
    genre: List[str] = []
    keywords: List[str] = []        # ★ 生图 / 文案的核心语料
    artStyle: ArtStyle = Field(default_factory=ArtStyle)
    factions: List[Faction] = []
    taboos: List[str] = []          # ★ 直接进生图 negative_prompt
    updatedAt: Optional[str] = None


class ProjectSettings(BaseModel):
    defaultCard: Dict[str, Any] = Field(
        default_factory=lambda: {"w": 745, "h": 1040, "dpi": 300, "bleed": 36,
                                 "w_mm": 63, "h_mm": 88})


class Project(BaseModel):
    id: str = Field(default_factory=lambda: new_id("p"))
    name: str = "新项目"
    description: str = ""
    tags: List[str] = []
    cover: Optional[str] = None             # assetId
    settings: ProjectSettings = Field(default_factory=ProjectSettings)
    # 创作简报（§4.4）：老 project.json 没有这个键时取默认空对象，向后兼容
    brief: ProjectBrief = Field(default_factory=ProjectBrief)
    createdAt: str = Field(default_factory=now_iso)
    updatedAt: str = Field(default_factory=now_iso)


class AssetItem(BaseModel):
    id: str = Field(default_factory=lambda: new_id("as"))
    type: Literal["icon", "font", "image", "baseplate"] = "image"
    name: str = ""
    library: Optional[str] = None           # icon 子库
    tags: List[str] = []
    ext: str = ".png"
    size: int = 0
    colorable: bool = False                 # SVG 可换色
    aiProvenance: Optional[BaseplateMeta] = None
    createdAt: str = Field(default_factory=now_iso)

    @property
    def rel_path(self) -> str:
        if self.type == "icon":
            return f"icons/{self.library or 'misc'}/{self.id}{self.ext}"
        if self.type == "font":
            return f"fonts/{self.id}{self.ext}"
        if self.type == "baseplate":
            return f"baseplates/{self.id}{self.ext}"
        return f"images/{self.id}{self.ext}"
