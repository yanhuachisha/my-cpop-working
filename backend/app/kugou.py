from __future__ import annotations

import ctypes
import os
import platform
import subprocess
import time
from ctypes import wintypes
from dataclasses import asdict, dataclass
from pathlib import Path
from threading import Lock

from pydantic import BaseModel, Field


_window_cache_lock = Lock()
_cached_kugou_window: int | None = None
_AUDIO_ACTIVE_THRESHOLD = 0.0005


@dataclass
class KugouNowPlaying:
    available: bool
    is_playing: bool
    title: str | None
    artist: str | None
    raw_title: str | None
    source: str


class KugouSearchRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    artist: str | None = Field(default=None, max_length=120)


def _empty(source: str = "windows-window-title") -> dict[str, object]:
    return asdict(KugouNowPlaying(False, False, None, None, None, source))


def _parse_window_title(raw_title: str) -> tuple[str | None, str | None]:
    cleaned = raw_title.strip()
    for suffix in (" - \u9177\u72d7\u97f3\u4e50", " - Kugou", "_\u9177\u72d7\u97f3\u4e50"):
        if cleaned.endswith(suffix):
            cleaned = cleaned[: -len(suffix)].strip(" -_")
    if not cleaned or cleaned in {"\u9177\u72d7\u97f3\u4e50", "Kugou", "\u9177\u72d7"}:
        return None, None
    for separator in (" - ", " \u2013 ", " \u2014 ", " | "):
        if separator in cleaned:
            artist, title = cleaned.split(separator, 1)
            return title.strip() or None, artist.strip() or None
    return cleaned, None


def _is_kugou_process_path(process_path: str | None) -> bool:
    if not process_path:
        return False
    executable = Path(process_path).name.lower()
    return executable in {"kugou.exe", "kugoumusic.exe", "kgmusic.exe"} or "kugou" in executable


def _window_process_path(hwnd: int) -> str | None:
    process_id = wintypes.DWORD()
    ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
    if not process_id.value:
        return None
    process = ctypes.windll.kernel32.OpenProcess(0x1000, False, process_id.value)
    if not process:
        return None
    try:
        buffer = ctypes.create_unicode_buffer(32768)
        size = wintypes.DWORD(len(buffer))
        if ctypes.windll.kernel32.QueryFullProcessImageNameW(process, 0, buffer, ctypes.byref(size)):
            return buffer.value
    finally:
        ctypes.windll.kernel32.CloseHandle(process)
    return None


def _window_title(hwnd: int) -> str | None:
    user32 = ctypes.windll.user32
    if not hwnd or not user32.IsWindow(hwnd) or not user32.IsWindowVisible(hwnd):
        return None
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return None
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, length + 1)
    title = buffer.value.strip()
    if not title or not _is_kugou_process_path(_window_process_path(hwnd)):
        return None
    return title


def _find_kugou_window_title() -> str | None:
    global _cached_kugou_window
    if platform.system() != "Windows":
        return None

    user32 = ctypes.windll.user32
    with _window_cache_lock:
        cached_title = _window_title(_cached_kugou_window or 0)
        if cached_title:
            return cached_title
        _cached_kugou_window = None

    matches: list[tuple[int, str]] = []
    enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def callback(hwnd: int, _lparam: int) -> bool:
        title = _window_title(hwnd)
        if title and ("\u9177\u72d7" in title or "kugou" in title.lower()):
            matches.append((hwnd, title))
            return False
        return True

    user32.EnumWindows(enum_proc(callback), 0)
    if not matches:
        return None
    with _window_cache_lock:
        _cached_kugou_window = matches[0][0]
    return matches[0][1]


def _find_kugou_window_handle() -> int | None:
    if platform.system() != "Windows":
        return None
    user32 = ctypes.windll.user32
    handles: list[int] = []
    enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def callback(hwnd: int, _lparam: int) -> bool:
        if not user32.IsWindowVisible(hwnd) or user32.GetWindowTextLengthW(hwnd) <= 0:
            return True
        if _is_kugou_process_path(_window_process_path(hwnd)):
            handles.append(hwnd)
            return False
        return True

    user32.EnumWindows(enum_proc(callback), 0)
    return handles[0] if handles else None


def _kugou_audio_active() -> bool | None:
    if platform.system() != "Windows":
        return None
    try:
        from pycaw.pycaw import AudioUtilities, IAudioMeterInformation
    except (ImportError, OSError):
        return None
    ole32 = ctypes.windll.ole32
    com_initialized = False
    try:
        ole32.CoInitialize(None)
        com_initialized = True
    except OSError:
        pass
    found_session = False
    try:
        for session in AudioUtilities.GetAllSessions():
            process = session.Process
            if not process:
                continue
            try:
                process_path = process.exe()
            except (OSError, RuntimeError, AttributeError):
                process_path = process.name()
            if not _is_kugou_process_path(process_path):
                continue
            found_session = True
            try:
                meter = session._ctl.QueryInterface(IAudioMeterInformation)
                if float(meter.GetPeakValue()) > _AUDIO_ACTIVE_THRESHOLD:
                    return True
            except (OSError, RuntimeError, AttributeError, ValueError):
                continue
    except (OSError, RuntimeError, AttributeError, getattr(ctypes, "COMError", OSError)):
        return None
    finally:
        if com_initialized:
            ole32.CoUninitialize()
    return False if found_session else None


def _set_clipboard_text(text: str) -> None:
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.SetClipboardData.restype = wintypes.HANDLE
    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = wintypes.LPVOID
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]

    encoded = (text + "\0").encode("utf-16-le")
    memory = kernel32.GlobalAlloc(0x0002, len(encoded))
    if not memory:
        raise OSError("无法分配剪贴板内存。")
    pointer = kernel32.GlobalLock(memory)
    if not pointer:
        kernel32.GlobalFree(memory)
        raise OSError("无法写入剪贴板。")
    ctypes.memmove(pointer, encoded, len(encoded))
    kernel32.GlobalUnlock(memory)

    for _ in range(8):
        if user32.OpenClipboard(None):
            break
        time.sleep(0.05)
    else:
        kernel32.GlobalFree(memory)
        raise OSError("剪贴板当前被其他程序占用。")
    try:
        user32.EmptyClipboard()
        if not user32.SetClipboardData(13, memory):
            raise OSError("无法设置剪贴板文本。")
        memory = None
    finally:
        user32.CloseClipboard()
        if memory:
            kernel32.GlobalFree(memory)


def _send_key(vk: int) -> None:
    user32 = ctypes.windll.user32
    user32.keybd_event(vk, 0, 0, 0)
    user32.keybd_event(vk, 0, 0x0002, 0)


def _send_shortcut(modifier: int, key: int) -> None:
    user32 = ctypes.windll.user32
    user32.keybd_event(modifier, 0, 0, 0)
    user32.keybd_event(key, 0, 0, 0)
    user32.keybd_event(key, 0, 0x0002, 0)
    user32.keybd_event(modifier, 0, 0x0002, 0)


def _focus_window(hwnd: int) -> bool:
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    foreground = user32.GetForegroundWindow()
    foreground_thread = user32.GetWindowThreadProcessId(foreground, None) if foreground else 0
    target_thread = user32.GetWindowThreadProcessId(hwnd, None)
    current_thread = kernel32.GetCurrentThreadId()
    attached_foreground = bool(
        foreground_thread and foreground_thread != current_thread
        and user32.AttachThreadInput(current_thread, foreground_thread, True)
    )
    attached_target = bool(
        target_thread and target_thread != current_thread
        and user32.AttachThreadInput(current_thread, target_thread, True)
    )
    try:
        user32.ShowWindowAsync(hwnd, 9)
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        user32.SetFocus(hwnd)
        time.sleep(0.2)
        return user32.GetForegroundWindow() == hwnd
    finally:
        if attached_target:
            user32.AttachThreadInput(current_thread, target_thread, False)
        if attached_foreground:
            user32.AttachThreadInput(current_thread, foreground_thread, False)


def get_now_playing() -> dict[str, object]:
    raw_title = _find_kugou_window_title()
    if not raw_title:
        return _empty()
    title, artist = _parse_window_title(raw_title)
    audio_active = _kugou_audio_active()
    is_playing = bool(title) if audio_active is None else bool(title and audio_active)
    source = "windows-kugou-process-title"
    if audio_active is not None:
        source = f"{source}+audio-session"
    return asdict(KugouNowPlaying(True, is_playing, title, artist, raw_title, source))


def open_kugou() -> dict[str, object]:
    if platform.system() != "Windows":
        return {"opened": False, "message": "\u5f53\u524d\u7cfb\u7edf\u4e0d\u662f Windows\uff0c\u65e0\u6cd5\u542f\u52a8\u672c\u5730\u9177\u72d7\u3002"}

    try:
        os.startfile("kugou://")
        return {"opened": True, "message": "\u5df2\u8bf7\u6c42\u6253\u5f00\u9177\u72d7\u97f3\u4e50\u3002"}
    except OSError:
        candidates = [
            Path(os.environ.get("ProgramFiles", "")) / "KuGou\\KuGou.exe",
            Path(os.environ.get("ProgramFiles(x86)", "")) / "KuGou\\KuGou.exe",
            Path(os.environ.get("LOCALAPPDATA", "")) / "KuGou\\KuGou.exe",
        ]
        for executable in candidates:
            if executable.is_file():
                subprocess.Popen([str(executable)], close_fds=True)
                return {"opened": True, "message": "\u5df2\u542f\u52a8\u9177\u72d7\u97f3\u4e50\u3002"}
    return {"opened": False, "message": "\u672a\u627e\u5230\u9177\u72d7\u97f3\u4e50\uff0c\u8bf7\u5148\u5b89\u88c5\u684c\u9762\u7248\u9177\u72d7\u3002"}


def search_kugou(request: KugouSearchRequest) -> dict[str, object]:
    query = " ".join(part for part in (request.artist, request.title) if part).strip()
    _set_clipboard_text(query)
    opened = open_kugou()
    message = (
        f"已打开酷狗，并复制：{query}"
        if opened["opened"]
        else f"已复制：{query}。{opened['message']}"
    )
    return {
        "opened": opened["opened"],
        "searched": False,
        "copied": True,
        "query": query,
        "direct_play": False,
        "message": message,
    }
