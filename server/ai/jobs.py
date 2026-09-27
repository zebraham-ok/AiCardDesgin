"""AI 任务表：内存 + 落盘（`workspace/jobs/*.json`），进程重启可查历史。

为什么要有它（§6.7）：图像生成动辄 40–200 s，不能让 HTTP 请求一直挂着；
前端 `POST` 拿到 jobId 后轮询进度即可。

实现取巧但够用：
  * 单进程内存字典 + 每次状态变化写一份 JSON（本地工具，无并发压力）；
  * 任务体是**同步**函数，用 `asyncio.to_thread` 丢到线程池跑，别堵事件循环；
  * 取消 = 放弃等待（结果到了也不写回）—— 因为 `n` 张图是一次 API 调用出的，
    没法半路掐断；这点在 UI 上要说明白。
"""
from __future__ import annotations

import asyncio
import json
import traceback
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .. import config

JOBS_DIR = config.WORKSPACE / "jobs"
JOBS_DIR.mkdir(parents=True, exist_ok=True)

_jobs: Dict[str, Dict[str, Any]] = {}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _path(job_id: str) -> Path:
    return JOBS_DIR / f"{job_id}.json"


def _persist(job: Dict[str, Any]) -> None:
    job["updatedAt"] = _now()
    try:
        tmp = _path(job["id"]).with_suffix(".json.tmp")
        tmp.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(_path(job["id"]))
    except OSError:
        pass          # 落盘失败不影响本次运行


def load_on_startup() -> int:
    """把上次进程留下的 running/pending 任务标成 interrupted（否则永远转圈）。"""
    n = 0
    for f in JOBS_DIR.glob("job_*.json"):
        try:
            job = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if job.get("status") in ("pending", "running"):
            job["status"] = "interrupted"
            job["error"] = "服务重启，任务中断（可重新生成）"
            _persist(job)
            n += 1
        _jobs[job["id"]] = job
    return n


def create(kind: str, pid: str, params: Dict[str, Any], total: int = 1) -> Dict[str, Any]:
    job: Dict[str, Any] = {
        "id": "job_" + uuid.uuid4().hex[:12],
        "kind": kind,                       # baseplate | cardart | text
        "pid": pid,
        "status": "pending",
        "progress": 0,
        "total": total,
        "images": [],                       # [{id, name, url, w, h}]
        "error": "",
        "params": params,
        "createdAt": _now(), "updatedAt": _now(),
    }
    _jobs[job["id"]] = job
    _persist(job)
    return job


def get(job_id: str) -> Optional[Dict[str, Any]]:
    if job_id in _jobs:
        return _jobs[job_id]
    p = _path(job_id)
    if p.exists():
        try:
            job = json.loads(p.read_text(encoding="utf-8"))
            _jobs[job_id] = job
            return job
        except (OSError, ValueError):
            return None
    return None


def update(job_id: str, **kw: Any) -> Optional[Dict[str, Any]]:
    job = get(job_id)
    if not job:
        return None
    job.update(kw)
    _persist(job)
    return job


def list_jobs(pid: Optional[str] = None, limit: int = 30) -> List[Dict[str, Any]]:
    items = [j for j in _jobs.values() if not pid or j.get("pid") == pid]
    return sorted(items, key=lambda j: j.get("createdAt", ""), reverse=True)[:limit]


async def run(job_id: str, fn: Callable[[], Dict[str, Any]]) -> None:
    """把同步任务体丢线程池执行，结果写回 job。

    `fn` 应返回：{"images": [...], "usage": {...}}，抛异常则任务转 error。
    """
    job = get(job_id)
    if not job:
        return
    update(job_id, status="running")
    try:
        result = await asyncio.to_thread(fn)
    except Exception as e:                       # noqa: BLE001 —— 任务边界，必须兜住
        cur = get(job_id) or {}
        if cur.get("status") != "canceled":
            update(job_id, status="error",
                   error=f"{type(e).__name__}: {e}",
                   trace=traceback.format_exc()[-1200:])
        return

    cur = get(job_id) or {}
    if cur.get("status") == "canceled":
        return                                   # 用户已放弃，结果丢弃
    images = result.get("images") or []
    update(job_id, status="done" if images else "error",
           images=images, progress=len(images), total=max(len(images), cur.get("total", 1)),
           usage=result.get("usage") or {}, meta=result.get("meta") or {},
           error="" if images else (result.get("error") or "没有生成任何图片"))
