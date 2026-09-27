"""一键启动：python run.py

关闭自动开浏览器：BGW_AUTO_OPEN=0
改端口：BGW_PORT=8780
"""
import threading
import webbrowser

import uvicorn

from server import config


def _auto_open() -> None:
    """延迟开浏览器，只在真正起服务时调用（TestClient 不会走到这里）。"""
    if not config.AUTO_OPEN_BROWSER:
        return
    threading.Timer(
        1.2, lambda: webbrowser.open(f"http://{config.HOST}:{config.PORT}/")
    ).start()


if __name__ == "__main__":
    print(f"[桌游设计工作坊] http://{config.HOST}:{config.PORT}")
    print(f"[数据目录] {config.WORKSPACE}")
    _auto_open()
    uvicorn.run("server.app:app", host=config.HOST, port=config.PORT,
                reload=False, log_level="info")
