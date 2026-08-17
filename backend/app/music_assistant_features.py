from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from app.data_store import get_store
from app.listener_memory import load_state

ROOT = Path(__file__).resolve().parents[2]
AUDIO_DIR = ROOT / "data" / "audio_jobs"
REPORT_DIR = ROOT / "data" / "weekly_reports"
MAX_UPLOAD_BYTES = 250 * 1024 * 1024


def _parse_time(value: object) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _recording_item(recording_id: str, extra: dict | None = None) -> dict | None:
    store = get_store()
    recording = store.get_recording(recording_id)
    if not recording:
        return None
    artist = store.get_artist(recording.artist_id)
    return {
        "recording_id": recording.id,
        "title": recording.title,
        "artist": artist.name if artist else "未知歌手",
        "moods": recording.moods,
        **(extra or {}),
    }


def emotion_memory(days: int = 14) -> dict:
    days = max(1, min(days, 90))
    cutoff = datetime.now(UTC) - timedelta(days=days)
    events = [
        event for event in load_state()["events"]
        if (_parse_time(event.get("at")) or datetime.min.replace(tzinfo=UTC)) >= cutoff
    ]
    actions: dict[str, Counter] = defaultdict(Counter)
    mood_scores: Counter = Counter()
    for event in events:
        recording_id = str(event.get("recording_id") or "")
        action = str(event.get("action") or "")
        if not recording_id:
            continue
        actions[recording_id][action] += 1
        item = _recording_item(recording_id)
        if not item or action not in {"play", "replay", "like", "save"}:
            continue
        weight = 3 if action in {"like", "save"} else 1
        mood_scores.update({mood: weight for mood in item["moods"]})

    avoided = []
    repeated = []
    for recording_id, counts in actions.items():
        item = _recording_item(recording_id)
        if not item:
            continue
        if counts["skip"]:
            avoided.append({**item, "skip_count": counts["skip"]})
        repeat_score = counts["replay"] + max(0, counts["play"] - 1)
        if repeat_score:
            repeated.append({**item, "repeat_count": repeat_score + 1})
    avoided.sort(key=lambda item: (-item["skip_count"], item["title"]))
    repeated.sort(key=lambda item: (-item["repeat_count"], item["title"]))

    top_moods = [{"mood": mood, "score": score} for mood, score in mood_scores.most_common(5)]
    summary = "最近还没有足够播放反馈。"
    if top_moods:
        summary = f"近 {days} 天更靠近「{'、'.join(item['mood'] for item in top_moods[:3])}」；"
        summary += f"循环线索 {len(repeated)} 首，切歌线索 {sum(item['skip_count'] for item in avoided)} 次。"
    return {
        "days": days,
        "generated_at": datetime.now(UTC).isoformat(),
        "signals": {
            "plays": sum(counts["play"] + counts["replay"] for counts in actions.values()),
            "pauses": sum(counts["pause"] for counts in actions.values()),
            "skips": sum(counts["skip"] for counts in actions.values()),
            "favorites": sum(counts["like"] + counts["save"] for counts in actions.values()),
        },
        "top_moods": top_moods,
        "repeat_tracks": repeated[:8],
        "avoid_tracks": avoided[:8],
        "summary": summary,
    }


def weekly_report(force: bool = False) -> dict:
    now = datetime.now(UTC)
    period_start = now - timedelta(days=7)
    previous_start = period_start - timedelta(days=7)
    report_path = REPORT_DIR / f"{now.astimezone().date().isoformat()}.json"
    if report_path.exists() and not force:
        try:
            return json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass

    current_events = []
    previous_events = []
    for event in load_state()["events"]:
        occurred_at = _parse_time(event.get("at"))
        if not occurred_at:
            continue
        if occurred_at >= period_start:
            current_events.append(event)
        elif occurred_at >= previous_start:
            previous_events.append(event)

    play_counts: Counter = Counter()
    mood_counts: Counter = Counter()
    previous_moods: Counter = Counter()
    time_slots: Counter = Counter()
    listened_seconds = 0.0
    slot_labels = ((5, "深夜"), (11, "上午"), (17, "下午"), (22, "夜晚"), (24, "深夜"))
    for event in current_events:
        if event.get("action") not in {"play", "replay"}:
            continue
        recording_id = str(event.get("recording_id") or "")
        play_counts[recording_id] += 1
        listened_seconds += float(event.get("listened_seconds") or (30 if event.get("channel") == "kugou-auto" else 0))
        occurred_at = _parse_time(event.get("at"))
        if occurred_at:
            hour = occurred_at.astimezone().hour
            time_slots[next(label for limit, label in slot_labels if hour < limit)] += 1
        item = _recording_item(recording_id)
        if item:
            mood_counts.update(item["moods"])
    for event in previous_events:
        if event.get("action") not in {"play", "replay"}:
            continue
        item = _recording_item(str(event.get("recording_id") or ""))
        if item:
            previous_moods.update(item["moods"])

    top_tracks = []
    for recording_id, count in play_counts.most_common(8):
        item = _recording_item(recording_id, {"play_count": count})
        if item:
            top_tracks.append(item)
    current_top = mood_counts.most_common(1)
    previous_top = previous_moods.most_common(1)
    mood_shift = "本周数据不足，继续听歌后会形成趋势。"
    if current_top:
        mood_shift = f"本周最常出现「{current_top[0][0]}」"
        if previous_top and previous_top[0][0] != current_top[0][0]:
            mood_shift += f"，上周更偏向「{previous_top[0][0]}」。"
        else:
            mood_shift += "，情绪偏好保持稳定。"

    report = {
        "period_start": period_start.astimezone().date().isoformat(),
        "period_end": now.astimezone().date().isoformat(),
        "generated_at": now.isoformat(),
        "local_only": True,
        "play_count": sum(play_counts.values()),
        "estimated_minutes": round(listened_seconds / 60),
        "top_tracks": top_tracks,
        "top_moods": [{"mood": mood, "count": count} for mood, count in mood_counts.most_common(5)],
        "time_slots": [{"label": label, "count": count} for label, count in time_slots.most_common()],
        "mood_shift": mood_shift,
    }
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    temporary_path = report_path.with_suffix(".tmp")
    temporary_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary_path.replace(report_path)
    return report


def _ffmpeg_executable() -> str | None:
    configured = os.getenv("FFMPEG_PATH")
    if configured and Path(configured).is_file():
        return configured
    installed = shutil.which("ffmpeg")
    if installed:
        return installed
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError, OSError):
        return None


def audio_status() -> dict:
    executable = _ffmpeg_executable()
    return {
        "available": bool(executable),
        "engine": "ffmpeg",
        "executable": executable,
        "operations": ["clip", "convert", "concat", "vocal_remove"],
        "local_only": True,
    }


def _safe_stem(filename: str | None, index: int) -> str:
    stem = Path(filename or f"audio-{index}").stem
    cleaned = re.sub(r"[^\w\-\u4e00-\u9fff]+", "-", stem, flags=re.UNICODE).strip("-")
    return cleaned[:70] or f"audio-{index}"


async def process_audio_files(
    files: list[UploadFile],
    operation: str,
    start_seconds: float,
    duration_seconds: float,
    output_format: str,
    base_url: str,
) -> dict:
    executable = _ffmpeg_executable()
    if not executable:
        raise RuntimeError("未找到 ffmpeg")
    if operation not in {"clip", "convert", "concat", "vocal_remove"}:
        raise ValueError("不支持的处理方式")
    if not files or len(files) > 20:
        raise ValueError("请选择 1 到 20 个音频文件")
    output_format = output_format if output_format in {"mp3", "wav", "m4a"} else "mp3"
    job_id = uuid4().hex
    job_dir = AUDIO_DIR / job_id
    input_dir = job_dir / "inputs"
    output_dir = job_dir / "outputs"
    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    input_paths = []
    total_bytes = 0
    for index, upload in enumerate(files, start=1):
        suffix = Path(upload.filename or "").suffix.lower() or ".audio"
        input_path = input_dir / f"{index:02d}-{_safe_stem(upload.filename, index)}{suffix}"
        with input_path.open("wb") as target:
            while chunk := await upload.read(1024 * 1024):
                total_bytes += len(chunk)
                if total_bytes > MAX_UPLOAD_BYTES:
                    raise ValueError("音频总大小不能超过 250 MB")
                target.write(chunk)
        input_paths.append(input_path)

    outputs: list[Path] = []
    commands: list[list[str]] = []
    codec = {"mp3": ["-c:a", "libmp3lame", "-b:a", "192k"], "wav": ["-c:a", "pcm_s16le"], "m4a": ["-c:a", "aac", "-b:a", "192k"]}[output_format]
    if operation == "clip":
        output = output_dir / f"{_safe_stem(files[0].filename, 1)}-片段.{output_format}"
        commands.append([executable, "-y", "-ss", str(max(0, start_seconds)), "-i", str(input_paths[0]), "-t", str(max(1, min(duration_seconds, 1800))), "-vn", "-ar", "44100", *codec, str(output)])
        outputs.append(output)
    elif operation == "convert":
        for index, input_path in enumerate(input_paths, start=1):
            output = output_dir / f"{_safe_stem(files[index - 1].filename, index)}.{output_format}"
            commands.append([executable, "-y", "-i", str(input_path), "-vn", "-ar", "44100", *codec, str(output)])
            outputs.append(output)
    elif operation == "concat":
        output = output_dir / f"无缝拼接.{output_format}"
        inputs = [part for path in input_paths for part in ("-i", str(path))]
        filter_inputs = "".join(f"[{index}:a]" for index in range(len(input_paths)))
        commands.append([executable, "-y", *inputs, "-filter_complex", f"{filter_inputs}concat=n={len(input_paths)}:v=0:a=1[out]", "-map", "[out]", "-ar", "44100", *codec, str(output)])
        outputs.append(output)
    else:
        output = output_dir / f"{_safe_stem(files[0].filename, 1)}-弱化人声.{output_format}"
        commands.append([executable, "-y", "-i", str(input_paths[0]), "-vn", "-af", "pan=stereo|c0=c0-c1|c1=c1-c0", "-ar", "44100", *codec, str(output)])
        outputs.append(output)

    for command in commands:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=300, check=False)
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr[-1200:] or "ffmpeg 处理失败")
    manifest = {
        "job_id": job_id,
        "operation": operation,
        "created_at": datetime.now(UTC).isoformat(),
        "outputs": [
            {
                "name": output.name,
                "size": output.stat().st_size,
                "download_url": f"{base_url}/api/agent/audio/files/{job_id}/{output.name}",
            }
            for output in outputs
        ],
    }
    (job_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def audio_output_path(job_id: str, filename: str) -> Path:
    if not re.fullmatch(r"[a-f0-9]{32}", job_id):
        raise ValueError("无效任务")
    output_dir = (AUDIO_DIR / job_id / "outputs").resolve()
    candidate = (output_dir / Path(filename).name).resolve()
    if candidate.parent != output_dir or not candidate.is_file():
        raise FileNotFoundError(filename)
    return candidate
