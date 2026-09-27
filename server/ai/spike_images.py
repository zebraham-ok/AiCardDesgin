"""M4 前置 Spike：图像生成的连通性 / 尺寸行为 / n / I2I 版面保持 / 提示词打磨。

为什么单独写这一支而不是直接进 M4a：
    正式 provider 抽象要等这些**未知数**落地才定得下来，尤其是
      ① 三个通道（OpenLux 中转 / 百炼兼容模式 / 百炼原生）各自到底认哪些参数；
      ② I2I 时输出尺寸是跟着参考图走，还是被 size 强制；
      ③ 中转分组对 n / size 的支持度差异。

用法（从项目根运行）：
    python -m server.ai.spike_images --plan size        # 尺寸与通道探针（便宜，先跑这个）
    python -m server.ai.spike_images --plan n           # n 支持度
    python -m server.ai.spike_images --plan i2i         # 图生图版面保持
    python -m server.ai.spike_images --plan prompt      # 底板提示词打磨（3 个变体）
    python -m server.ai.spike_images --plan all

产物全部落在 `workspace/spike/<时间戳>/`：
    index.md       人看的对比表
    results.json   机器读的明细（含耗时 / 用量 / 原始响应片段）
    images/*.png   生成结果（拿到 URL 立刻下载落盘，不依赖 24h 有效期）
    refs/*.png     用的布局参考图

注意：这是**花钱**的脚本（qwen-image 约 $0.00118/张）。每个 plan 的图数在下面 CASES 里能看清。
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import pathlib
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server import config  # noqa: E402  （顺带加载 .env）

try:  # Windows 控制台默认 GBK，中文输出会炸
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ---------------------------------------------------------------------------
# 常量：通道与模型
# ---------------------------------------------------------------------------
OPENLUX_BASE = "https://api.openlux.ai/v1"
# 百炼：手册里新域名形如 https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com
# 旧域名仍可用（Key 与地域绑定），这里两个都试，看哪个通
DASHSCOPE_BASES = [
    "https://dashscope.aliyuncs.com",
]
TIMEOUT = httpx.Timeout(600.0, connect=20.0)

MODEL_QWEN_PRO = "qwen-image-3.0-pro"
MODEL_QWEN = "qwen-image-3.0"
MODEL_WAN_PRO = "wan2.7-image-pro"

# 卡牌净尺寸（63×88mm @300DPI）；AI 侧按同比例放大一档
CARD_W, CARD_H = 745, 1040
AI_W, AI_H = 1024, 1424          # 同比例（0.719 vs 0.716），且面积 ≤ 2.25M 走 1K 计费档
KAREA = AI_W * AI_H


# ---------------------------------------------------------------------------
# 结果记录
# ---------------------------------------------------------------------------
@dataclass
class Shot:
    case: str
    provider: str
    model: str
    note: str = ""
    size_req: Optional[str] = None
    n_req: int = 1
    ref: Optional[str] = None
    elapsed: float = 0.0
    ok: bool = False
    status: Optional[int] = None
    error: str = ""
    images: List[Dict[str, Any]] = field(default_factory=list)   # {file, w, h, bytes}
    usage: Dict[str, Any] = field(default_factory=dict)
    raw_head: str = ""
    prompt: str = ""


# ---------------------------------------------------------------------------
# 布局参考图（§6.4.2 第 ③ 步）—— Pillow 合成，不给模型看真字
# ---------------------------------------------------------------------------
# 示例模板「法术卡」的区域（设计像素，坐标系与 canvas.w/h 一致）
ZONES = [
    ("卡名区", "text", (60, 70, 620, 70)),
    ("费用区", "number", (640, 60, 70, 70)),
    ("卡图区", "image", (60, 170, 625, 430)),
    ("描述区", "text", (60, 630, 625, 300)),
]


def build_layout_ref(w: int, h: int, path: pathlib.Path,
                     labels: bool = False, zones: Optional[List] = None,
                     src_w: int = CARD_W, src_h: int = CARD_H) -> pathlib.Path:
    """把模板区域画成"布局参考图"：中灰底 + 分区线框。**不渲染任何文字**。

    视觉语言（踩过三次坑，别随意改）：
      * **只描边、不填充**。早期给分区填了色块，模型会直接**照抄填充色**：
        图片区填绿斜纹 → 它在那儿画满一幅插画；填浅灰 → 它把整块涂成白板。
        纯线稿参考图下模型才会把"底色"当成要替换的目标。
      * **不要写字**（`labels=False` 是默认值）。参考图里一旦有"卡名/留空"这类标签，
        出图会把它们当成内容模仿出来，在卡面上留下误导性的文字痕迹。
        区域语义改由**提示词文本**描述（`prompt.describe_zones()`），
        图上只保留线型区分：文字/数值区 = 细实线，图片/图标区 = 虚线。
      * 缺省区域表 `ZONES` 只是探索用的示例，生产路径请传 `zones_from_template(tpl)`。

    刻意输出**不带透明通道**的 PNG：万相明确不接受带 alpha 的图。
    """
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (w, h), (222, 222, 222))
    d = ImageDraw.Draw(img, "RGBA")
    sx, sy = w / src_w, h / src_h           # 从设计像素换算到目标尺寸
    for name, kind, (x, y, rw, rh) in (zones if zones is not None else ZONES):
        box = (x * sx, y * sy, (x + rw) * sx, (y + rh) * sy)
        empty = kind in ("image", "icon")
        x0, y0, x1, y1 = box
        if empty:
            dash, gap, xx = 16, 10, x0
            while xx < x1:                      # 上下虚线
                d.line([(xx, y0), (min(xx + dash, x1), y0)], fill=(120, 120, 120, 255), width=2)
                d.line([(xx, y1), (min(xx + dash, x1), y1)], fill=(120, 120, 120, 255), width=2)
                xx += dash + gap
            yy = y0
            while yy < y1:                      # 左右虚线
                d.line([(x0, yy), (x0, min(yy + dash, y1))], fill=(120, 120, 120, 255), width=2)
                d.line([(x1, yy), (x1, min(yy + dash, y1))], fill=(120, 120, 120, 255), width=2)
                yy += dash + gap
        else:
            d.rectangle(box, outline=(96, 96, 96, 255), width=2)
        if labels:
            # 只在调试时打开：文字会被模型模仿进成品，生产路径务必保持 False
            d.text((box[0] + 8, box[1] + 8),
                   "留空" if empty else name, fill=(70, 70, 70, 255))
    d.rectangle((int(w * 0.03), int(h * 0.03), int(w * 0.97), int(h * 0.97)),
                outline=(150, 150, 150, 180), width=2)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
    return path


def zones_from_template(tpl: Any) -> List[tuple]:
    """从真实模板的字段生成布局参考图用的区域表（跳过隐形定位框）。"""
    fields = [f for f in (getattr(tpl, "fields", None) or []) if not getattr(f, "guide", False)]
    if not fields:
        fields = list(getattr(tpl, "fields", None) or [])
    fields.sort(key=lambda f: (f.rect[1], f.rect[0]))
    out = []
    for f in fields:
        out.append((f.label or f.key, f.kind, tuple(float(v) for v in f.rect[:4])))
    return out


def data_url(p: pathlib.Path) -> str:
    mime = "image/png" if p.suffix.lower() == ".png" else "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(p.read_bytes()).decode()}"


# ---------------------------------------------------------------------------
# 三个通道
# ---------------------------------------------------------------------------
def _post(url: str, headers: Dict[str, str], payload: Dict[str, Any],
          files: Optional[Dict[str, Any]] = None) -> httpx.Response:
    with httpx.Client(timeout=TIMEOUT) as c:
        if files is not None:
            return c.post(url, headers=headers, data=payload, files=files)
        return c.post(url, headers=headers, json=payload)


def call_openlux(prompt: str, size: Optional[str], n: int, refs: List[str],
                 model: str = MODEL_QWEN_PRO, seed: Optional[int] = None,
                 negative: str = "", extra: Optional[Dict[str, Any]] = None,
                 edits: bool = False, base: str = OPENLUX_BASE) -> Dict[str, Any]:
    """OpenLux 中转（OpenAI 协议）。refs 非空时走图生图。

    OpenAI 协议里图生图有两种写法，中转站实现不一：
      * `/v1/images/generations` + JSON 里的 `image: [dataURL, ...]`（qwen 系列常见）
      * `/v1/images/edits` multipart（官方是给 gpt-image 的）
    这里按 `edits` 开关切换，方便对照。
    """
    hdr = {"Authorization": f"Bearer {config.OPENLUX_KEY}"}
    body: Dict[str, Any] = {"model": model, "prompt": prompt, "n": n}
    if size:
        body["size"] = size
    if seed is not None:
        body["seed"] = seed
    if negative:
        body["negative_prompt"] = negative
    if extra:
        body.update(extra)

    if refs and edits:
        data = {k: str(v) for k, v in body.items() if k != "image"}
        files = [("image", (f"ref{i}.png", base64.b64decode(r.split(",", 1)[1]), "image/png"))
                 for i, r in enumerate(refs)]
        resp = _post(f"{base}/images/edits", hdr, data, files=files)
    else:
        if refs:
            body["image"] = refs if len(refs) > 1 else refs[0]
        resp = _post(f"{base}/images/generations", hdr, body)
    return {"status": resp.status_code, "body": _safe_json(resp)}


def call_dashscope_compat(prompt: str, size: Optional[str], n: int, refs: List[str],
                          model: str = MODEL_QWEN_PRO, seed: Optional[int] = None,
                          negative: str = "", extra: Optional[Dict[str, Any]] = None,
                          base: str = DASHSCOPE_BASES[0]) -> Dict[str, Any]:
    """百炼 OpenAI 兼容模式。注意 size 分隔符是**字母 x**，扩展字段要进 extra_body。"""
    hdr = {"Authorization": f"Bearer {config.ALIYUN_MULTIMODAL_KEY}"}
    body: Dict[str, Any] = {"model": model, "prompt": prompt, "n": n}
    if size:
        body["size"] = size
    if seed is not None:
        body["seed"] = seed
    if refs:
        body["image"] = refs if len(refs) > 1 else refs[0]
    ext = {"watermark": False}
    if negative:
        ext["negative_prompt"] = negative
    if extra:
        ext.update(extra)
    body["extra_body"] = ext
    resp = _post(f"{base}/compatible-mode/v1/images/generations", hdr, body)
    return {"status": resp.status_code, "body": _safe_json(resp)}


def call_dashscope_native(prompt: str, size: Optional[str], n: int, refs: List[str],
                          model: str = MODEL_QWEN_PRO, seed: Optional[int] = None,
                          negative: str = "", extra: Optional[Dict[str, Any]] = None,
                          base: str = DASHSCOPE_BASES[0]) -> Dict[str, Any]:
    """百炼 DashScope 原生协议。I2I：content = [ {image}, {text} ]（1–3 张图 + 1 段文本）。

    size 分隔符是**星号**（`1024*1424`），与兼容模式的字母 x 不同 —— 踩坑清单第 1 条。
    """
    hdr = {"Authorization": f"Bearer {config.ALIYUN_MULTIMODAL_KEY}",
           "Content-Type": "application/json"}
    content: List[Dict[str, str]] = [{"image": r} for r in refs]
    content.append({"text": prompt})
    params: Dict[str, Any] = {"n": n, "watermark": False}
    if size:
        params["size"] = size.replace("x", "*")
        if "*" not in params["size"]:
            params["size"] = size
    if seed is not None:
        params["seed"] = seed
    if negative:
        params["negative_prompt"] = negative
    if extra:
        params.update(extra)
    body = {"model": model,
            "input": {"messages": [{"role": "user", "content": content}]},
            "parameters": params}
    resp = _post(f"{base}/api/v1/services/aigc/multimodal-generation/generation", hdr, body)
    return {"status": resp.status_code, "body": _safe_json(resp)}


def _safe_json(resp: httpx.Response) -> Any:
    try:
        return resp.json()
    except Exception:
        return {"_text": resp.text[:1500]}


PROVIDERS = {
    "openlux": call_openlux,
    "compat": call_dashscope_compat,
    "native": call_dashscope_native,
}


# ---------------------------------------------------------------------------
# 从响应里抠出图 URL / b64
# ---------------------------------------------------------------------------
def extract_images(body: Any) -> List[str]:
    """兼容三种返回形态：OpenAI `data[].url|b64_json`、DashScope 原生 `output.choices[]`。"""
    out: List[str] = []
    if not isinstance(body, dict):
        return out
    for item in body.get("data") or []:
        if not isinstance(item, dict):
            continue
        if item.get("url"):
            out.append(item["url"])
        elif item.get("b64_json"):
            out.append("b64:" + item["b64_json"])
    try:
        for ch in (body.get("output") or {}).get("choices") or []:
            for c in ((ch.get("message") or {}).get("content") or []):
                if isinstance(c, dict) and c.get("image"):
                    out.append(c["image"])
    except Exception:
        pass
    return out


def extract_usage(body: Any) -> Dict[str, Any]:
    u = (body or {}).get("usage") if isinstance(body, dict) else None
    return u if isinstance(u, dict) else {}


def save_image(src: str, dest_dir: pathlib.Path, name: str) -> Dict[str, Any]:
    """URL 立刻下载落盘（结果 URL 只有 24h），返回 {file,w,h,bytes}。"""
    from PIL import Image
    if src.startswith("b64:"):
        raw = base64.b64decode(src[4:])
    else:
        with httpx.Client(timeout=TIMEOUT, follow_redirects=True) as c:
            r = c.get(src)
            r.raise_for_status()
            raw = r.content
    dest_dir.mkdir(parents=True, exist_ok=True)
    p = dest_dir / f"{name}.png"
    img = Image.open(io.BytesIO(raw))
    img.save(p)
    return {"file": str(p.relative_to(ROOT)).replace("\\", "/"),
            "w": img.width, "h": img.height, "bytes": len(raw)}


# ---------------------------------------------------------------------------
# 用例
# ---------------------------------------------------------------------------
BASE_PROMPT = ("一张奇幻风格的桌游卡牌背景板：深色羊皮纸质感，边缘装饰性的暗金藤蔓纹样，"
               "整体色调沉稳。")

PROMPT_VARIANTS = {
    "V1-朴素": BASE_PROMPT + "不要出现任何文字。",
    "V2-分区": (
        "生成一张奇幻风格的桌游卡牌背景板。整体为深色羊皮纸质感，色调沉稳，"
        "边缘有暗金色装饰性藤蔓纹样。版面分区要求：顶部横向条带用于放置卡牌名称，"
        "请保持平整、低对比度、大面积留白，便于后续叠加文字；"
        "中偏右上方的小方块用于放置数值，同样保持干净留白；"
        "画面中部的大矩形区域是主画面区，请在这里绘制一幅完整的、细节丰富的奇幻场景插画；"
        "画面下部的大面积区域用于放置说明文字，请保持平整、低对比度、大面积留白。"
        "禁止出现任何文字、字母、数字、水印、签名或logo。"),
    "V3-强约束": (
        "一张奇幻风格的桌游卡牌背景板，竖版构图。材质为深色做旧羊皮纸，"
        "主色为深棕与暗金，少量青绿色点缀。边缘环绕一圈暗金色细藤蔓纹样，"
        "不要粗重的画框边框。版面自上而下分为四段："
        "① 顶部约 8% 高度是一条平整的窄横带，仅做轻微材质渐变，不放任何图案细节；"
        "② 再往下约 8% 高度是标题区留白，颜色均匀、对比度低；"
        "③ 中部约 40% 高度是主画面区，绘制一幅完整的奇幻场景插画（远山、古堡、雾气），"
        "细节丰富、层次分明；"
        "④ 底部约 40% 高度是大面积平整留白区，颜色均匀、对比度低，仅保留极轻微纸纹。"
        "画面中严禁出现任何文字、字母、数字、符号、水印、签名、徽标、边框或装饰性字母。"
        "所有留白区域必须干净、平整、无杂乱细节。")
}

NEGATIVE = "文字, 汉字, 字母, 数字, 水印, 签名, logo, 边框, 相框, 杂乱细节, 文字块"

# --- 第二轮：按第一轮的结论改进（方位+用途点名，不写百分比；显式禁画框） ---
_ZONES_V4 = (
    "版面自上而下必须严格保留以下四个区域，位置、比例、边界与参考图一致：\n"
    "① 顶部横向窄条带（画面上方约一成高度）：卡名区，平整、低对比、大面积留白，只保留极轻纸纹；\n"
    "② 该条带最右侧的独立小方块（约一成宽度）：数值区，小方格内部干净平整、颜色均匀；\n"
    "③ 中部大矩形（约占画面四成高度）：主画面区，绘制一幅完整、细节丰富、有景深的场景插画；\n"
    "④ 底部大区域（约占画面四成高度）：说明文字区，大面积平整留白，颜色均匀、对比度低。"
)

PROMPT_VARIANTS["V4-点名分区"] = (
    "生成一张竖版桌游卡牌背景板，尺寸与参考图完全一致，严格保留参考图的版面结构。"
    "整体为深色做旧羊皮纸质感，主色为深棕与暗金；边缘只做轻微的材质加深过渡，"
    "不要画框、不要相框线、不要粗重的装饰边框。" + _ZONES_V4 +
    "主画面区绘制一幅完整的奇幻场景插画（远山、古堡、雾气、幽绿微光），层次分明。"
    "严禁出现任何文字、字母、数字、符号、水印、签名、徽标或装饰性字母。"
)

PROMPT_VARIANTS["V5-注入项目语料"] = (
    # 这一段模拟 §6.11 里由 ProjectBrief 拼出来的语料块
    "[风格] 厚涂数字绘画，笔触粗犷、边缘做旧。\n"
    "[氛围] 史诗、冷峻。\n"
    "[主色板] #0b1a2b 作底、#12314f 作中景、#c9a227 收边点缀、#e2e8f0 作高光，"
    "整体冷色，避免高饱和霓虹。\n"
    "[题材关键词] 星际、舰队、资源争夺、遗迹。\n"
    "生成一张竖版桌游卡牌背景板，尺寸与参考图完全一致，严格保留参考图的版面结构。"
    "整体为做旧金属与羊皮纸混合质感，边缘只做轻微的材质加深过渡，"
    "不要画框、不要相框线、不要粗重的装饰边框。" + _ZONES_V4 +
    "主画面区绘制一幅完整的星际场景插画（残破的巨型遗迹、远处的舰队剪影、"
    "漂浮的尘埃与幽蓝色数据流），层次分明、有景深。"
    "严禁出现任何文字、字母、数字、符号、水印、签名、徽标或装饰性字母。"
)


#: 项目没填 ProjectBrief 时用的演示语料，保证 `--plan real` 总能验证到"有语料"的情况
_DEMO_BRIEF = {
    "title": "星域争霸", "oneLiner": "争夺星区资源的快节奏对抗卡牌",
    "synopsis": "旧帝国崩溃后，各派系在破碎星区争夺遗迹与航道。",
    "genre": ["卡牌对战", "资源管理"],
    "keywords": ["星际", "舰队", "遗迹", "资源争夺"],
    "artStyle": {"style": "厚涂数字绘画", "details": "笔触粗犷、边缘做旧",
                 "palette": ["#0b1a2b", "#12314f", "#c9a227", "#e2e8f0"],
                 "mood": ["史诗", "冷峻"]},
    "factions": [{"name": "铁壁议会", "desc": "重工业、冷灰蓝", "color": "#5a6b7c"}],
    "taboos": ["不要文字", "不要霓虹高饱和"],
}


def real_case(outdir: pathlib.Path) -> Optional[Dict[str, Any]]:
    """生产路径验证：参考图由**模板字段**生成、提示词由 `server.ai.prompt` 拼。

    这条链路才是 M4b 真正要跑的东西；前面的 V1–V5 是手写提示词的探索。
    """
    from server.store import repo as _repo
    from server.ai import prompt as _prompt

    for p in _repo.list_projects():
        pid = p["id"]
        tpls = _repo.list_templates(pid)
        if not tpls:
            continue
        tpl = _repo.get_template(pid, tpls[0]["id"])
        if not tpl or not tpl.fields:
            continue
        proj = _repo.get_project(pid)
        brief = proj.brief if proj else None
        used = "项目自带 brief"
        if not (getattr(brief, "keywords", None)
                or getattr(getattr(brief, "artStyle", None), "style", "")):
            brief = _DEMO_BRIEF
            used = "内置演示语料（该项目没填 brief）"
        zones = zones_from_template(tpl)
        ref = build_layout_ref(tpl.canvas.w, tpl.canvas.h,
                               outdir / "refs" / f"layout_{tpl.canvas.w}x{tpl.canvas.h}.png",
                               zones=zones, src_w=tpl.canvas.w, src_h=tpl.canvas.h)
        prompt, negative = _prompt.build_baseplate_prompt(tpl, brief)
        print(f"真实模板：{(proj.name if proj else pid)} / {tpl.name}　语料来源：{used}")
        print("区域：" + " | ".join(f"{n}({k})" for n, k, _ in zones))
        print("\n---- 拼出的提示词 ----\n" + prompt + "\n----------------------\n")
        return dict(case="真实路径·底板留空", prov="openlux", prompt=prompt,
                    size=f"{tpl.canvas.w}x{tpl.canvas.h}", n=1, refs=[str(ref)],
                    model=MODEL_QWEN_PRO, note="图片位留空版（生产路径）",
                    negative=negative, seed=42)
    return None


def plan_cases(plan: str, ref_small: pathlib.Path, ref_ai: pathlib.Path,
               providers: List[str]) -> List[Dict[str, Any]]:
    """返回用例列表；每个用例 = 一次 API 调用。"""
    cases: List[Dict[str, Any]] = []

    def add(case, prov, prompt, size=None, n=1, refs=None, model=MODEL_QWEN_PRO,
            note="", **kw):
        cases.append(dict(case=case, prov=prov, prompt=prompt, size=size, n=n,
                          refs=refs, model=model, note=note, **kw))

    if plan in ("size", "all"):
        for p in providers:
            add("尺寸·指定1024x1424", p, BASE_PROMPT, size="1024x1424",
                note="看是否严格按请求尺寸出图")
            add("尺寸·auto", p, BASE_PROMPT, size="auto",
                note="auto 时模型自选分辨率，比例可能不是卡牌比例")
        if "openlux" in providers:
            add("尺寸·非1024档(745x1040)", "openlux", BASE_PROMPT, size="745x1040",
                note="试非 1024 系尺寸能否被接受")
            add("尺寸·宽高反了", "openlux", BASE_PROMPT, size="1424x1024",
                note="横版对照")
    if plan in ("n", "all"):
        for p in providers:
            add("n=4", p, BASE_PROMPT, size="1024x1424", n=4,
                note="中转分组是否支持 n>1；耗时是否翻倍")
    if plan in ("i2i", "all"):
        for p in providers:
            add("I2I·参考图745x1040·不指定size", p, BASE_PROMPT, size=None,
                refs=[str(ref_small)], note="输出比例是否跟随参考图")
            add("I2I·参考图745x1040·指定1024x1424", p, BASE_PROMPT,
                size="1024x1424", refs=[str(ref_small)], note="size 是否覆盖参考图比例")
            add("I2I·参考图1024x1424·不指定size", p, BASE_PROMPT, size=None,
                refs=[str(ref_ai)], note="换成 AI 档参考图再试")
        add("I2I·参考图745x1040·指定745x1040", "openlux", BASE_PROMPT,
            size="745x1040", refs=[str(ref_small)], note="能否像素级贴合模板")
        add("I2I·万相2K", "native", BASE_PROMPT, size="2K",
            refs=[str(ref_small)], model=MODEL_WAN_PRO, note="万相对照（贵 40 倍）")
    if plan in ("prompt", "prompt2", "all"):
        # 用最终生产路径的参数测：尺寸 = 模板净尺寸（像素级贴合 + 最便宜计费档），
        # 参考图 = 745×1040 布局图；固定 seed 减少随机性便于比对提示词
        variants = PROMPT_VARIANTS
        if plan == "prompt2":
            variants = {k: v for k, v in PROMPT_VARIANTS.items() if k.startswith("V4") or k.startswith("V5")}
        for name, prompt in variants.items():
            add(f"提示词·{name}", "openlux", prompt, size=f"{CARD_W}x{CARD_H}",
                refs=[str(ref_small)], negative=NEGATIVE, seed=42,
                note="同一张布局参考图 + 固定 seed，比较版面遵守度与留白")
    return cases


# ---------------------------------------------------------------------------
# 跑
# ---------------------------------------------------------------------------
def run(case: Dict[str, Any], outdir: pathlib.Path, idx: int) -> Shot:
    prov = case["prov"]
    refs = [data_url(pathlib.Path(r)) for r in (case.get("refs") or [])]
    shot = Shot(case=case["case"], provider=prov, model=case["model"],
                note=case.get("note", ""), size_req=case.get("size"),
                n_req=case.get("n", 1), ref=(case.get("refs") or [None])[0],
                prompt=case["prompt"])
    t0 = time.perf_counter()
    try:
        fn = PROVIDERS[prov]
        r = fn(case["prompt"], case.get("size"), case.get("n", 1), refs,
               model=case["model"], negative=case.get("negative", ""),
               seed=case.get("seed"), extra=case.get("extra"))
        shot.status = r["status"]
        body = r["body"]
        shot.raw_head = json.dumps(body, ensure_ascii=False)[:1200]
        urls = extract_images(body)
        shot.usage = extract_usage(body)
        if shot.status != 200 or not urls:
            shot.error = f"HTTP {shot.status}: " + shot.raw_head[:400]
        else:
            for i, u in enumerate(urls):
                try:
                    shot.images.append(
                        save_image(u, outdir / "images",
                                   f"{idx:02d}_{prov}_{case['case']}_{i + 1}"))
                except Exception as e:  # 下载失败也算失败，因为 URL 24h 会过期
                    shot.error += f" 下载第{i + 1}张失败: {e}"
            shot.ok = bool(shot.images)
    except Exception as e:
        shot.error = f"{type(e).__name__}: {e}"
    shot.elapsed = round(time.perf_counter() - t0, 1)
    return shot


def write_report(outdir: pathlib.Path, shots: List[Shot], meta: Dict[str, Any]) -> None:
    (outdir / "results.json").write_text(
        json.dumps({"meta": meta, "shots": [asdict(s) for s in shots]},
                   ensure_ascii=False, indent=2), encoding="utf-8")

    lines = ["# 图像生成 Spike 结果", "",
             f"时间：{meta['started']}　计划：{meta['plan']}　"
             f"用例：{len(shots)}　成功：{sum(1 for s in shots if s.ok)}", ""]
    lines += ["| 用例 | 通道 | 模型 | 请求 size | 请求 n | 实得张数 | 实际尺寸 | 耗时 | 状态 |",
              "|---|---|---|---|---|---|---|---|---|"]
    for s in shots:
        dims = " / ".join(f"{i['w']}×{i['h']}" for i in s.images) or "—"
        state = "✅" if s.ok else "❌"
        lines.append(f"| {s.case} | {s.provider} | {s.model} | {s.size_req or '未指定'} | "
                     f"{s.n_req} | {len(s.images)} | {dims} | {s.elapsed}s | {state} |")
    lines += ["", "## 用量明细（计费档位）", ""]
    for s in shots:
        if s.usage:
            lines.append(f"- `{s.provider}` / {s.case}："
                         f"{json.dumps(s.usage, ensure_ascii=False)}")
    lines += ["", "## 失败与原始响应", ""]
    for s in shots:
        if not s.ok:
            lines += [f"### {s.provider} · {s.case}", "", "```", s.error, "```", ""]
    lines += ["", "## 提示词变体（用于人工比对）", ""]
    for name, p in PROMPT_VARIANTS.items():
        lines += [f"**{name}**", "", f"> {p}", ""]
    lines += ["", "图片在 `images/`，参考图在 `refs/`。"]
    (outdir / "index.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", default="size",
                    choices=["size", "n", "i2i", "prompt", "prompt2", "real", "all"])
    ap.add_argument("--providers", default="openlux",
                    help="逗号分隔：openlux,compat,native")
    ap.add_argument("--tag", default="", help="输出目录后缀，便于分组")
    args = ap.parse_args()

    providers = [p.strip() for p in args.providers.split(",") if p.strip()]
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    suffix = f"_{args.tag}" if args.tag else ""
    outdir = ROOT / "workspace" / "spike" / f"{ts}{suffix}"
    (outdir / "refs").mkdir(parents=True, exist_ok=True)

    keys = {"openlux": bool(config.OPENLUX_KEY),
            "compat": bool(config.ALIYUN_MULTIMODAL_KEY),
            "native": bool(config.ALIYUN_MULTIMODAL_KEY)}
    missing = [p for p in providers if not keys.get(p)]
    if missing:
        print(f"[warn] 这些通道没有 Key，会被跳过：{missing}")

    ref_small = build_layout_ref(CARD_W, CARD_H, outdir / "refs" / "layout_745x1040.png")
    ref_ai = build_layout_ref(AI_W, AI_H, outdir / "refs" / "layout_1024x1424.png")
    print(f"布局参考图：{ref_small}\n           {ref_ai}")

    if args.plan == "real":
        # 生产路径：参考图来自真实模板字段，提示词来自 server/ai/prompt.py
        one = real_case(outdir)
        cases = [one] if one and keys.get(one["prov"]) else []
    else:
        cases = [c for c in plan_cases(args.plan, ref_small, ref_ai, providers)
                 if c["prov"] in providers and keys.get(c["prov"])]
    print(f"计划 {args.plan}：{len(cases)} 个用例\n")
    shots: List[Shot] = []
    for i, case in enumerate(cases, 1):
        print(f"[{i}/{len(cases)}] {case['prov']:8s} {case['case']} ...", flush=True)
        s = run(case, outdir, i)
        shots.append(s)
        dims = " / ".join(f"{im['w']}×{im['h']}" for im in s.images) or "—"
        print(f"        → {'OK ' if s.ok else 'FAIL'} {len(s.images)} 张 {dims} "
              f"{s.elapsed}s" + (f"  {s.error[:160]}" if s.error else ""), flush=True)

    write_report(outdir, shots, {"plan": args.plan, "providers": providers,
                                 "started": datetime.now().isoformat(timespec="seconds"),
                                 "card_px": [CARD_W, CARD_H], "ai_px": [AI_W, AI_H]})
    ok = sum(1 for s in shots if s.ok)
    print(f"\n完成：{ok}/{len(shots)} 成功　→　{outdir}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
