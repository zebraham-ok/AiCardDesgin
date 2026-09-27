"""图像生成 provider：OpenLux（主通道）+ DashScope 原生（备选），带重试。

参数与坑全部来自 2026-09-27 的 Spike 实测（见 `项目计划.md` §6.10 与进度盘点）：
  * `size` 必须显式传（省略会被放大到 2K 档）；
  * 不支持 `auto`；
  * 百炼兼容模式在旧域名是 404，必须走原生协议；
  * I2I 比 T2I 慢一倍多，且**长请求会偶发断连** → 必须重试。

同步实现（httpx.Client）。调用方在 FastAPI 里用 `asyncio.to_thread` 包一层，
不要让同步 HTTP 阻塞事件循环。
"""
from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from .. import config

OPENLUX_BASE = "https://api.openlux.ai/v1"
DASHSCOPE_BASE = "https://dashscope.aliyuncs.com"
TIMEOUT = httpx.Timeout(600.0, connect=20.0)

DEFAULT_IMAGE_MODEL = "qwen-image-3.0-pro"
FALLBACK_IMAGE_MODEL = "qwen-image-3.0"

RETRY_STATUS = {429, 500, 502, 503, 504}


@dataclass
class GenResult:
    ok: bool = False
    urls: List[str] = field(default_factory=list)
    provider: str = ""
    model: str = ""
    elapsed: float = 0.0
    usage: Dict[str, Any] = field(default_factory=dict)
    error: str = ""
    attempts: int = 0
    status: Optional[int] = None
    raw_head: str = ""


def data_url(path: Path | str) -> str:
    p = Path(path)
    mime = {
        ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }.get(p.suffix.lower(), "image/png")
    return f"data:{mime};base64,{base64.b64encode(p.read_bytes()).decode()}"


def _extract_images(body: Any) -> List[str]:
    """兼容 OpenAI `data[].url|b64_json` 与 DashScope 原生 `output.choices[].message.content[]`。"""
    out: List[str] = []
    if not isinstance(body, dict):
        return out
    for item in body.get("data") or []:
        if isinstance(item, dict):
            if item.get("url"):
                out.append(item["url"])
            elif item.get("b64_json"):
                out.append("b64:" + item["b64_json"])
    for ch in ((body.get("output") or {}).get("choices") or []):
        for c in ((ch.get("message") or {}).get("content") or []):
            if isinstance(c, dict) and c.get("image"):
                out.append(c["image"])
    return out


def _usage(body: Any) -> Dict[str, Any]:
    u = body.get("usage") if isinstance(body, dict) else None
    return u if isinstance(u, dict) else {}


# ---------------------------------------------------------------------------
# 通道
# ---------------------------------------------------------------------------
def _openlux(prompt: str, size: str, n: int, refs: List[str], model: str,
             negative: str, seed: Optional[int]) -> httpx.Response:
    body: Dict[str, Any] = {"model": model, "prompt": prompt, "n": n, "size": size,
                            "watermark": False}
    if refs:
        body["image"] = refs if len(refs) > 1 else refs[0]
    if negative:
        body["negative_prompt"] = negative
    if seed is not None:
        body["seed"] = seed
    return httpx.post(f"{OPENLUX_BASE}/images/generations",
                      headers={"Authorization": f"Bearer {config.OPENLUX_KEY}"},
                      json=body, timeout=TIMEOUT)


def _dashscope_native(prompt: str, size: str, n: int, refs: List[str], model: str,
                      negative: str, seed: Optional[int]) -> httpx.Response:
    content: List[Dict[str, str]] = [{"image": r} for r in refs]
    content.append({"text": prompt})
    params: Dict[str, Any] = {"n": n, "watermark": False, "size": size.replace("x", "*")}
    if negative:
        params["negative_prompt"] = negative
    if seed is not None:
        params["seed"] = seed
    return httpx.post(
        f"{DASHSCOPE_BASE}/api/v1/services/aigc/multimodal-generation/generation",
        headers={"Authorization": f"Bearer {config.ALIYUN_MULTIMODAL_KEY}",
                 "Content-Type": "application/json"},
        json={"model": model,
              "input": {"messages": [{"role": "user", "content": content}]},
              "parameters": params},
        timeout=TIMEOUT)


PROVIDERS = {"openlux": _openlux, "dashscope": _dashscope_native}


def provider_for(model: str) -> str:
    """模型 → 通道。wan 系列只在百炼，其余默认走 OpenLux（便宜）。"""
    return "dashscope" if str(model).startswith("wan") else "openlux"


# ---------------------------------------------------------------------------
# 统一入口（带重试）
# ---------------------------------------------------------------------------
def generate(prompt: str, size: str, n: int = 1, refs: Optional[List[str]] = None,
             model: str = DEFAULT_IMAGE_MODEL, negative: str = "",
             seed: Optional[int] = None, provider: Optional[str] = None,
             retries: int = 3) -> GenResult:
    """生成图像。`refs` 非空即图生图（I2I）。失败自动重试（断连/5xx/限流）。"""
    refs = refs or []
    provider = provider or provider_for(model)
    fn = PROVIDERS[provider]
    res = GenResult(provider=provider, model=model)
    t0 = time.perf_counter()

    for attempt in range(1, retries + 1):
        res.attempts = attempt
        try:
            r = fn(prompt, size, n, refs, model, negative, seed)
            res.status = r.status_code
            try:
                body = r.json()
            except Exception:
                body = {"_text": r.text[:800]}
            res.raw_head = json.dumps(body, ensure_ascii=False)[:800]
            urls = _extract_images(body)
            res.usage = _usage(body)
            if r.status_code == 200 and urls:
                res.ok = True
                res.urls = urls
                break
            if r.status_code in RETRY_STATUS:
                res.error = f"HTTP {r.status_code}: {res.raw_head[:300]}"
            else:
                # 参数错/鉴权错，重试没意义
                res.error = f"HTTP {r.status_code}: {res.raw_head[:300]}"
                break
        except (httpx.RemoteProtocolError, httpx.ReadTimeout, httpx.ConnectError,
                httpx.ReadError, httpx.PoolTimeout) as e:
            res.error = f"{type(e).__name__}: {e}"      # 实测 I2I 会偶发断连
        except Exception as e:
            res.error = f"{type(e).__name__}: {e}"
            break

        if attempt < retries:
            time.sleep(min(2 ** attempt, 8))            # 2s / 4s / 8s

    res.elapsed = round(time.perf_counter() - t0, 1)
    if not res.ok and not res.error:
        res.error = "未返回任何图像"
    return res
