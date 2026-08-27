from __future__ import annotations

import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path


CREATE_NO_WINDOW = 0x08000000
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200


def project_root() -> Path:
    candidates = []
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).resolve().parent)
        configured_root = os.getenv("CPOP_PROJECT_ROOT")
        if configured_root:
            candidates.append(Path(configured_root))
        candidates.append(Path(r"C:\ide\game\jay"))
    else:
        candidates.append(Path(__file__).resolve().parents[1])
    for candidate in candidates:
        if (candidate / "backend" / "app" / "main.py").is_file() and (candidate / "frontend" / "package.json").is_file():
            return candidate
    return candidates[0]


ROOT = project_root()
LOG_DIR = ROOT / ".launcher"


def port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.4):
            return True
    except OSError:
        return False


def backend_ready() -> bool:
    try:
        with urllib.request.urlopen("http://127.0.0.1:8001/api/listening/settings", timeout=1.2) as response:
            payload = response.read()
            return response.status == 200 and b"core_prompt" in payload and b"default_core_prompt" in payload
    except (OSError, urllib.error.HTTPError, urllib.error.URLError):
        return False


def listening_process_ids(port: int) -> list[int]:
    try:
        output = subprocess.check_output(
            ["netstat", "-ano", "-p", "tcp"],
            text=True,
            encoding="utf-8",
            errors="ignore",
            creationflags=CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    process_ids = []
    for line in output.splitlines():
        if "LISTENING" not in line or not re.search(rf":{port}\s", line):
            continue
        parts = line.split()
        if parts and parts[-1].isdigit():
            process_ids.append(int(parts[-1]))
    return list(dict.fromkeys(process_ids))


def process_command_line(process_id: int) -> str:
    command = (
        f"(Get-CimInstance Win32_Process -Filter 'ProcessId={process_id}').CommandLine"
    )
    try:
        return subprocess.check_output(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
            text=True,
            encoding="utf-8",
            errors="ignore",
            creationflags=CREATE_NO_WINDOW,
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def stop_stale_backend() -> None:
    process_ids = listening_process_ids(8001)
    if not process_ids:
        return
    for process_id in process_ids:
        command_line = process_command_line(process_id).casefold()
        if "uvicorn" not in command_line or "app.main:app" not in command_line:
            raise RuntimeError("8001 端口被其他程序占用，请先关闭该程序。")
        subprocess.run(
            ["taskkill.exe", "/PID", str(process_id), "/T", "/F"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=CREATE_NO_WINDOW,
        )
    deadline = time.monotonic() + 5
    while port_open(8001) and time.monotonic() < deadline:
        time.sleep(0.2)


def stop_stale_frontend() -> None:
    process_ids = listening_process_ids(3000)
    if not process_ids:
        return
    frontend_path = str((ROOT / "frontend").resolve()).casefold()
    for process_id in process_ids:
        command_line = process_command_line(process_id).casefold()
        if frontend_path not in command_line or "start-server.js" not in command_line:
            raise RuntimeError("3000 端口被其他程序占用，请先关闭该程序。")
        subprocess.run(
            ["taskkill.exe", "/PID", str(process_id), "/T", "/F"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=CREATE_NO_WINDOW,
        )
    deadline = time.monotonic() + 5
    while port_open(3000) and time.monotonic() < deadline:
        time.sleep(0.2)


def executable(candidates: list[str]) -> str | None:
    for candidate in candidates:
        expanded = os.path.expandvars(candidate)
        if Path(expanded).is_file():
            return expanded
        discovered = shutil.which(expanded)
        if discovered:
            return discovered
    return None


def start_hidden(command: list[str], cwd: Path, log_name: str, env: dict[str, str] | None = None) -> None:
    LOG_DIR.mkdir(exist_ok=True)
    output = (LOG_DIR / f"{log_name}.out.log").open("a", encoding="utf-8")
    error = (LOG_DIR / f"{log_name}.err.log").open("a", encoding="utf-8")
    try:
        subprocess.Popen(
            command,
            cwd=str(cwd),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=error,
            creationflags=CREATE_NO_WINDOW | DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
            close_fds=True,
        )
    finally:
        output.close()
        error.close()


def start_backend() -> None:
    if port_open(8001):
        stop_stale_backend()
    python = executable([
        os.getenv("CPOP_PYTHON", ""),
        r"C:\ide\anaconda\python.exe",
        "python.exe",
    ])
    if not python:
        raise RuntimeError("未找到 Python，请设置环境变量 CPOP_PYTHON。")
    env = os.environ.copy()
    # Desktop startup uses the production Agent runtime; unavailable Redis/ES/model
    # dependencies degrade to deterministic local behavior instead of blocking launch.
    env.setdefault("AGENT_PLATFORM_ENABLED", "true")
    env.setdefault("KUGOU_DESKTOP_INTEGRATION", "true")
    env.setdefault("MODEL_SERVICE_URL", "http://127.0.0.1:8010")
    env.setdefault("ELASTICSEARCH_URL", "http://127.0.0.1:9200")
    env.setdefault("MUSIC_CORE_URL", "http://127.0.0.1:8080")
    env.setdefault("REDIS_URL", "redis://127.0.0.1:6379/0")
    start_hidden(
        [python, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"],
        ROOT / "backend",
        "backend",
        env,
    )


def start_frontend() -> None:
    if port_open(3000):
        stop_stale_frontend()
    npm = executable([os.getenv("CPOP_NPM", ""), "npm.cmd"])
    if not npm:
        raise RuntimeError("未找到 npm，请设置环境变量 CPOP_NPM。")
    env = os.environ.copy()
    env["NEXT_PUBLIC_API_BASE_URL"] = "http://localhost:8001"
    start_hidden(
        [npm, "run", "dev", "--", "--hostname", "0.0.0.0", "--port", "3000"],
        ROOT / "frontend",
        "frontend",
        env,
    )


def start_bridge_if_installed() -> None:
    if port_open(9191):
        return
    bridge_app = ROOT / ".local" / "kugou-bridge" / "app.js"
    node = executable(["node.exe"])
    if bridge_app.is_file() and node:
        start_hidden([node, str(bridge_app)], bridge_app.parent, "kugou-bridge")


def start_catalog_refresh() -> None:
    python = executable([
        os.getenv("CPOP_PYTHON", ""),
        r"C:\ide\anaconda\python.exe",
        "python.exe",
    ])
    refresh_script = ROOT / "scripts" / "refresh_catalog.py"
    if python and refresh_script.is_file():
        start_hidden([python, str(refresh_script)], ROOT, "catalog-refresh")


def open_kugou() -> None:
    try:
        os.startfile("kugou://")
        return
    except OSError:
        pass
    candidates = [
        r"C:\software\KGMusic\KuGou.exe",
        r"%ProgramFiles%\KuGou\KuGou.exe",
        r"%ProgramFiles(x86)%\KuGou\KuGou.exe",
        r"%LOCALAPPDATA%\KuGou\KuGou.exe",
    ]
    kugou = executable(candidates)
    if kugou:
        subprocess.Popen([kugou], creationflags=CREATE_NO_WINDOW, close_fds=True)


def wait_for_web(timeout_seconds: float = 45) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if port_open(3000) and backend_ready():
            return True
        time.sleep(0.5)
    return False


def message(title: str, body: str, error: bool = False) -> None:
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(0, body, title, 0x10 if error else 0x40)
    except (AttributeError, OSError):
        pass


def main() -> int:
    try:
        start_backend()
        start_frontend()
        start_bridge_if_installed()
        open_kugou()
        if not wait_for_web():
            raise RuntimeError("服务启动超时，请查看项目 .launcher 目录中的日志。")
        start_catalog_refresh()
        webbrowser.open("http://localhost:3000", new=2)
        return 0
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        message("My C-Pop Working 启动失败", str(error), error=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
