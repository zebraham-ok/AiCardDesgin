"""AI 相关 API（M4）。

当前落地的是**语料层**部分（§6.11）：
  * `POST /api/projects/{pid}/preview-prompt` —— 只读预览，把 ProjectBrief + 模板
    拼成最终 prompt / negative_prompt，供「项目设定」抽屉与 AI 面板展示。
  * `GET  /api/ai/health` / `GET /api/ai/models` —— 通道与能力表（含 Spike 实测结论）。

真正的生图/生文调用（job 队列 + 结果落盘）随后接上。
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import config
from ..ai import jobs
from ..ai import layout_ref
from ..ai import prompt as P
from ..ai import providers
from ..ai import sink
from ..store import repo

router = APIRouter(prefix="/api", tags=["ai"])


# ---------------------------------------------------------------------------
# 能力表（来源：2026-09-27 Spike 实测，见 plan §6.10 / 进度盘点）
# ---------------------------------------------------------------------------
MODELS: Dict[str, Dict[str, Any]] = {
    "qwen-image-3.0-pro": {
        "provider": "openlux", "kind": "image", "pricePerImage": 0.00118,
        "supports": {"n": [1, 6], "size": "WxH（严格遵守，含 745x1040 这类非 1024 档）",
                     "auto": False, "i2i": True, "seed": True, "negativePrompt": True},
        "note": "底板与卡图首选；实测 I2I 约 75-172s，T2I 约 36-47s，n=4 并行",
    },
    "qwen-image-3.0": {
        "provider": "openlux", "kind": "image", "pricePerImage": 0.00118,
        "supports": {"n": [1, 6], "size": "WxH", "auto": False, "i2i": True,
                     "seed": True, "negativePrompt": True},
        "note": "同上，略快",
    },
    "wan2.7-image-pro": {
        "provider": "dashscope", "kind": "image", "pricePerImage": 0.0478,
        "supports": {"n": [1, 4], "size": "1K/2K/4K 或 W*H（星号）", "auto": False,
                     "i2i": True, "seed": True, "negativePrompt": True,
                     "color_palette": True, "bbox_list": True},
        "note": "仅在需要 color_palette / bbox_list / 4K 时用，贵 40 倍",
    },
    "qwen-plus": {
        "provider": "dashscope-text", "kind": "text",
        "supports": {"json_object": True},
        "note": "文生文主力",
    },
}

#: 通道连通性（只报"有没有 Key"，不在这里发请求，避免健康检查被拖慢）
PROVIDERS = {
    "openlux": {"base": "https://api.openlux.ai/v1", "key": "OPENLUX",
                "images": "/images/generations", "configured": bool(config.OPENLUX_KEY)},
    "dashscope": {"base": "https://dashscope.aliyuncs.com", "key": "ALIYUN_MULTIMODAL",
                  "images": "/api/v1/services/aigc/image-generation/generation",
                  "configured": bool(config.ALIYUN_MULTIMODAL_KEY),
                  "note": "兼容模式 /compatible-mode/v1 在旧域名是 404，必须走原生协议"},
    "dashscope-text": {"base": "https://dashscope.aliyuncs.com", "key": "ALIYUN_TEXT",
                       "configured": bool(config.ALIYUN_TEXT_KEY)},
}


# ---------------------------------------------------------------------------
# 提示词预览
# ---------------------------------------------------------------------------
class PreviewBody(BaseModel):
    kind: str = "baseplate"          # baseplate | cardart | text
    templateId: Optional[str] = None
    cardId: Optional[str] = None
    fieldKey: str = ""               # kind=cardart 时：往哪个图片字段里放
    subject: str = ""                # 用户临时补充的画面描述（可选）
    extra: str = ""                  # 用户临时追加的一句提示词（可选）


def _load(pid: str, tid: Optional[str], cid: Optional[str]):
    proj = repo.get_project(pid)
    if not proj:
        raise HTTPException(404, "项目不存在")
    t = tid
    if not t:
        tpls = repo.list_templates(pid)
        t = tpls[0]["id"] if tpls else None
    tpl = repo.get_template(pid, t) if t else None
    card = repo.get_card(pid, cid) if cid else None
    return proj, tpl, card


@router.post("/projects/{pid}/preview-prompt")
def preview_prompt(pid: str, body: PreviewBody):
    """把项目设定 + 模板（+卡牌）拼成最终提示词（只读，不调模型、不扣费）。"""
    proj, tpl, card = _load(pid, body.templateId, body.cardId)
    if body.kind in ("baseplate", "cardart") and not tpl:
        raise HTTPException(400, "还没有模板，先建一个模板再预览提示词")
    return P.preview(proj.brief, tpl, card, kind=body.kind, subject=body.subject,
                     extra=body.extra, field_key=body.fieldKey)


# ---------------------------------------------------------------------------
# 生成：模板底板 / 卡牌配图
# ---------------------------------------------------------------------------
class GenBody(BaseModel):
    templateId: Optional[str] = None
    cardId: Optional[str] = None
    fieldKey: str = ""
    n: int = 4                       # 候选数量
    extra: str = ""                  # 临时追加的一句提示词
    subject: str = ""
    model: str = ""                  # 留空用默认（qwen-image-3.0-pro）
    seed: Optional[int] = None
    useLayoutRef: bool = True        # 底板：是否带布局参考图做 I2I


def _ref_hash(p) -> Optional[str]:
    try:
        import hashlib
        return hashlib.sha1(open(p, "rb").read()).hexdigest()[:16]
    except OSError:
        return None


def _baseplate_file(tpl: Any):
    """模板底板的实际文件路径（没底板 / 文件丢了返回 None）。

    用于「底板 → 进 AI 参考图」：把现有底板垫在参考图底下，
    给的是"基于当前底板改良"而不是"从零再来"。
    """
    from pathlib import Path as _Path

    aid = (tpl.background or {}).get("assetId")
    a = repo.get_asset(aid) if aid else None
    if not a:
        return None
    p = _Path(config.ASSETS_DIR) / a.rel_path
    return p if p.exists() else None


@router.post("/projects/{pid}/ai/baseplate")
async def gen_baseplate(pid: str, body: GenBody):
    """模板底板生成：布局参考图 + 提示词 → n 张候选（异步 job）。

    图片位在提示词里被明确要求留空 —— 底片只出"外壳"，每张卡的配图后面单独生成。
    """
    proj, tpl, _ = _load(pid, body.templateId, None)
    if not tpl:
        raise HTTPException(400, "模板不存在")
    model = body.model or providers.DEFAULT_IMAGE_MODEL
    size = P.baseplate_size(tpl)
    prompt, negative = P.build_baseplate_prompt(tpl, proj.brief, extra=body.extra,
                                                subject=body.subject)

    ref_path = None
    if body.useLayoutRef and layout_ref.zones_from_template(tpl):
        out = config.WORKSPACE / "jobs" / "refs"
        # 「底板 → 进 AI 参考图」打开时，把现有底板垫在参考图底下（改良/局部重画）
        base = _baseplate_file(tpl) if (tpl.background or {}).get("aiRef") else None
        ref_path = layout_ref.ref_for_template(
            tpl, out / f"{tpl.id}_{size}{'_base' if base else ''}.png", base_image=base)

    job = jobs.create("baseplate", pid, {
        "templateId": tpl.id, "size": size, "n": body.n, "model": model,
        "prompt": prompt, "negativePrompt": negative, "extra": body.extra,
        "useLayoutRef": bool(ref_path),
    }, total=body.n)

    def work() -> Dict[str, Any]:
        refs = [providers.data_url(ref_path)] if ref_path else []
        res = providers.generate(prompt, size, n=body.n, refs=refs, model=model,
                                 negative=negative, seed=body.seed)
        if not res.ok:
            return {"images": [], "error": f"{res.error}（重试 {res.attempts} 次）"}
        items = sink.save_images(
            res.urls, kind="baseplate", name_prefix=f"{tpl.name}_底板",
            provenance={"provider": res.provider, "model": res.model, "prompt": prompt,
                        "negativePrompt": negative, "seed": body.seed, "size": size,
                        "refImageHash": _ref_hash(ref_path) if ref_path else None},
            tags=["ai", "baseplate", tpl.name])
        return {"images": [{"id": a.id, "name": a.name, "url": f"/api/assets/{a.id}/file"}
                           for a in items],
                "usage": res.usage,
                "meta": {"size": size, "provider": res.provider, "model": res.model,
                         "elapsed": res.elapsed, "attempts": res.attempts}}

    asyncio.create_task(jobs.run(job["id"], work))
    return {"jobId": job["id"], "size": size, "prompt": prompt,
            "negativePrompt": negative, "useLayoutRef": bool(ref_path)}


@router.post("/projects/{pid}/ai/cardart")
async def gen_cardart(pid: str, body: GenBody):
    """卡牌配图生成（T2I）。尺寸取**该图片字段的区域大小**，prompt 里带上卡面文字。"""
    proj, tpl, card = _load(pid, body.templateId, body.cardId)
    if not tpl:
        raise HTTPException(400, "模板不存在")
    if not card:
        raise HTTPException(400, "卡牌不存在")
    model = body.model or providers.DEFAULT_IMAGE_MODEL
    size = P.cardart_size(tpl, body.fieldKey)
    prompt, negative = P.build_cardart_prompt(card, tpl, proj.brief,
                                              field_key=body.fieldKey, extra=body.extra)

    job = jobs.create("cardart", pid, {
        "templateId": tpl.id, "cardId": card.id, "fieldKey": body.fieldKey,
        "size": size, "n": body.n, "model": model, "prompt": prompt,
        "negativePrompt": negative, "extra": body.extra,
    }, total=body.n)

    def work() -> Dict[str, Any]:
        res = providers.generate(prompt, size, n=body.n, model=model,
                                 negative=negative, seed=body.seed)
        if not res.ok:
            return {"images": [], "error": f"{res.error}（重试 {res.attempts} 次）"}
        items = sink.save_images(
            res.urls, kind="image", name_prefix=f"{card.name}_配图",
            provenance={"provider": res.provider, "model": res.model, "prompt": prompt,
                        "negativePrompt": negative, "seed": body.seed, "size": size},
            tags=["ai", "cardart", card.name])
        return {"images": [{"id": a.id, "name": a.name, "url": f"/api/assets/{a.id}/file"}
                           for a in items],
                "usage": res.usage,
                "meta": {"size": size, "provider": res.provider, "model": res.model,
                         "elapsed": res.elapsed, "attempts": res.attempts}}

    asyncio.create_task(jobs.run(job["id"], work))
    return {"jobId": job["id"], "size": size, "prompt": prompt,
            "negativePrompt": negative}


@router.get("/ai/jobs/{job_id}")
def job_detail(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "任务不存在")
    return job


@router.get("/ai/jobs")
def job_list(pid: str = "", limit: int = 20):
    return jobs.list_jobs(pid or None, limit=limit)


@router.post("/ai/jobs/{job_id}/cancel")
def job_cancel(job_id: str):
    """放弃等待。注意：n 张图是一次 API 调用出的，这里只能丢弃结果，无法中途掐断请求。"""
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "任务不存在")
    if job["status"] in ("pending", "running"):
        jobs.update(job_id, status="canceled", error="已取消（忽略这次结果）")
    return jobs.get(job_id)


@router.post("/projects/{pid}/ai/baseplate/apply")
def baseplate_apply(pid: str, templateId: str, assetId: str):
    """把选中的候选设为模板背景。

    关键：同时记下 `bleedPx` —— 底板是按**含出血尺寸**生成的，渲染器据此做
    "像素 1:1 对齐"（出血模式铺满整张、净尺寸模式从中间裁），不再有任何缩放。
    """
    tpl = repo.get_template(pid, templateId)
    if not tpl:
        raise HTTPException(404, "模板不存在")
    if not repo.get_asset(assetId):
        raise HTTPException(404, "资源不存在")
    old_id = (tpl.background or {}).get("assetId")
    bg = {**(tpl.background or {}), "assetId": assetId, "fit": "cover",
          "bleedPx": P.bleed_px(tpl)}
    if old_id and old_id != assetId:
        # 换了另一张图，旧图上的挖空区域位置就没意义了（同图重应用则保留）
        bg.pop("mask", None)
    tpl.background = bg
    repo.save_template(tpl)
    return {"ok": True, "background": tpl.background}


# ---------------------------------------------------------------------------
# 状态与能力
# ---------------------------------------------------------------------------
@router.get("/ai/health")
def ai_health():
    return {"providers": {k: {kk: vv for kk, vv in v.items() if kk != "key"}
                          for k, v in PROVIDERS.items()},
            "models": list(MODELS),
            "ready": any(p["configured"] for p in PROVIDERS.values())}


@router.get("/ai/models")
def ai_models():
    return MODELS
