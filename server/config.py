"""全局配置：路径、端口、默认卡规格。

优先级：环境变量 > .env > 默认值
"""
from __future__ import annotations

import os
from pathlib import Path

# server/config.py -> 项目根
ROOT = Path(__file__).resolve().parents[1]


def _load_dotenv() -> None:
    """极简 .env 加载，避免为这一个功能引入依赖。"""
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())


_load_dotenv()

# ---- 数据目录 -------------------------------------------------------------
WORKSPACE = Path(os.getenv("BGW_WORKSPACE", ROOT / "workspace")).resolve()
ASSETS_DIR = WORKSPACE / "assets"
PROJECTS_DIR = WORKSPACE / "projects"

for _d in (WORKSPACE, ASSETS_DIR, PROJECTS_DIR,
           ASSETS_DIR / "icons", ASSETS_DIR / "fonts",
           ASSETS_DIR / "baseplates", ASSETS_DIR / "images"):
    _d.mkdir(parents=True, exist_ok=True)

# ---- 服务 -----------------------------------------------------------------
HOST = os.getenv("BGW_HOST", "127.0.0.1")
PORT = int(os.getenv("BGW_PORT", "8770"))
AUTO_OPEN_BROWSER = os.getenv("BGW_AUTO_OPEN", "1") != "0"

# ---- 默认卡规格（63x88mm @300DPI） ---------------------------------------
DEFAULT_CARD = {"w": 745, "h": 1040, "dpi": 300, "bleed": 36,
                "w_mm": 63, "h_mm": 88}

# ---- AI（M4 才启用；此处仅占位，未配置时前端自动灰度禁用） ----------------
OPENLUX_KEY = os.getenv("OPENLUX", "")
ALIYUN_MULTIMODAL_KEY = os.getenv("ALIYUN_MULTIMODAL", "")
ALIYUN_TEXT_KEY = os.getenv("ALIYUN_TEXT", "")
