from __future__ import annotations

import json
import os
import time
import hashlib
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Lock, get_ident
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from app.data_store import get_store
from app.listening_history import (
    record_daily_listening as record_daily_listening_sqlite,
    today_listening_stats as today_listening_stats_sqlite,
)

STATE_PATH = Path(__file__).resolve().parents[2] / "data" / "listener_state.json"
_lock = Lock()

class FeedbackRequest(BaseModel):
    recording_id: str
    action: Literal["play", "like", "save", "skip", "replay", "pause"]
    channel: str = "daily"
    listened_seconds: float | None = Field(default=None, ge=0, le=86_400)


def _empty() -> dict:
    return {
        "events": [], "liked": [], "like_counts": {}, "saved": [], "skipped": [], "play_counts": {},
        "favorite_timestamps": {}, "lyric_fragments": [], "music_notes": [],
        "listening_conversations": {}, "agent_sessions": {}, "daily_listening": {},
        "listening_companion_prompt": "",
        "listening_companion_core_prompt": "",
    }



class LyricFragmentRequest(BaseModel):
    excerpt: str = Field(min_length=1, max_length=500)
    song_title: str | None = None
    artist: str | None = None
    note: str | None = Field(default=None, max_length=300)


class MusicNoteRequest(BaseModel):
    content: str = Field(min_length=1, max_length=2000)
    prompt: str | None = Field(default=None, max_length=300)
    song_title: str | None = Field(default=None, max_length=200)
    artist: str | None = Field(default=None, max_length=120)
    album: str | None = Field(default=None, max_length=200)


def _write_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = STATE_PATH.with_name(
        f".{STATE_PATH.name}.{os.getpid()}.{get_ident()}.{uuid4().hex}.tmp"
    )
    try:
        temporary_path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        for attempt in range(5):
            try:
                os.replace(temporary_path, STATE_PATH)
                return
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.05 * (attempt + 1))
    finally:
        temporary_path.unlink(missing_ok=True)


def save_lyric_fragment(request: LyricFragmentRequest) -> dict:
    with _lock:
        state = load_state()
        fragment = {
            "id": f"lyric-{int(datetime.now(UTC).timestamp() * 1000)}", "excerpt": request.excerpt.strip(),
            "song_title": request.song_title, "artist": request.artist, "note": request.note,
            "saved_at": datetime.now(UTC).isoformat(),
        }
        state["lyric_fragments"] = [fragment, *state.get("lyric_fragments", [])][:200]
        _write_state(state)
    return fragment


def lyric_fragments() -> list[dict]:
    return load_state().get("lyric_fragments", [])

def save_music_note(request: MusicNoteRequest) -> dict:
    with _lock:
        state = load_state()
        note = {
            "id": f"note-{int(datetime.now(UTC).timestamp() * 1000)}",
            "content": request.content.strip(),
            "prompt": request.prompt.strip() if request.prompt else None,
            "song_title": request.song_title,
            "artist": request.artist,
            "album": request.album,
            "saved_at": datetime.now(UTC).isoformat(),
        }
        state["music_notes"] = [note, *state.get("music_notes", [])][:500]
        _write_state(state)
    return note


def music_notes() -> list[dict]:
    return load_state().get("music_notes", [])


def get_listening_companion_prompt() -> str:
    return str(load_state().get("listening_companion_prompt") or "").strip()


def save_listening_companion_prompt(prompt: str) -> str:
    normalized = prompt.strip()
    with _lock:
        state = load_state()
        state["listening_companion_prompt"] = normalized
        _write_state(state)
    return normalized


def get_listening_companion_core_prompt() -> str:
    return str(load_state().get("listening_companion_core_prompt") or "").strip()


def save_listening_companion_core_prompt(prompt: str) -> str:
    normalized = prompt.strip()
    with _lock:
        state = load_state()
        state["listening_companion_core_prompt"] = normalized
        _write_state(state)
    return normalized


def _agent_session_summary(session: dict) -> dict:
    messages = session.get("messages", [])
    last_message = messages[-1].get("content", "") if messages else ""
    return {
        "id": session.get("id"),
        "title": session.get("title") or "新对话",
        "preview": last_message[:80],
        "message_count": len(messages),
        "created_at": session.get("created_at"),
        "updated_at": session.get("updated_at"),
    }


def create_agent_session(title: str | None = None) -> dict:
    created_at = datetime.now(UTC).isoformat()
    session_id = f"agent-{uuid4().hex}"
    session = {
        "id": session_id,
        "title": (title or "新对话").strip()[:60] or "新对话",
        "messages": [],
        "created_at": created_at,
        "updated_at": created_at,
    }
    with _lock:
        state = load_state()
        state.setdefault("agent_sessions", {})[session_id] = session
        _write_state(state)
    return _agent_session_summary(session)


def agent_sessions() -> list[dict]:
    sessions = [
        _agent_session_summary(session)
        for session in load_state().get("agent_sessions", {}).values()
    ]
    return sorted(sessions, key=lambda item: item.get("updated_at") or "", reverse=True)


def agent_session(session_id: str) -> dict | None:
    session = load_state().get("agent_sessions", {}).get(session_id)
    if not session:
        return None
    return {**_agent_session_summary(session), "messages": list(session.get("messages", []))}


def save_agent_session_turn(
    session_id: str,
    user_content: str,
    assistant_content: str,
    tools_used: list[str] | None = None,
    model: str | None = None,
) -> dict:
    saved_at = datetime.now(UTC).isoformat()
    with _lock:
        state = load_state()
        sessions = state.setdefault("agent_sessions", {})
        session = sessions.get(session_id)
        if not session:
            session = {
                "id": session_id,
                "title": "新对话",
                "messages": [],
                "created_at": saved_at,
                "updated_at": saved_at,
            }
            sessions[session_id] = session
        if session.get("title") in {None, "", "新对话"}:
            compact_title = " ".join(user_content.strip().split())
            session["title"] = compact_title[:28] + ("…" if len(compact_title) > 28 else "")
        session["messages"] = [
            *session.get("messages", []),
            {
                "id": f"user-{uuid4().hex}",
                "role": "user",
                "content": user_content.strip(),
                "saved_at": saved_at,
            },
            {
                "id": f"assistant-{uuid4().hex}",
                "role": "assistant",
                "content": assistant_content.strip(),
                "tools_used": list(tools_used or []),
                "model": model,
                "saved_at": saved_at,
            },
        ][-120:]
        session["updated_at"] = saved_at
        _write_state(state)
    return {**_agent_session_summary(session), "messages": list(session["messages"])}


def delete_agent_session(session_id: str) -> bool:
    with _lock:
        state = load_state()
        sessions = state.setdefault("agent_sessions", {})
        removed = sessions.pop(session_id, None)
        if removed is None:
            return False
        _write_state(state)
    return True


def _conversation_key(song_title: str, artist: str | None) -> str:
    identity = f"{song_title.strip().casefold()}::{(artist or '').strip().casefold()}"
    return hashlib.sha1(identity.encode("utf-8")).hexdigest()


def listening_conversation(song_title: str, artist: str | None = None) -> list[dict]:
    if not song_title.strip():
        return []
    state = load_state()
    conversation = state.get("listening_conversations", {}).get(_conversation_key(song_title, artist), {})
    return list(conversation.get("messages", []))


def save_listening_conversation_turn(
    song_title: str,
    artist: str | None,
    question: str,
    answer: str,
    turn_id: str | None = None,
) -> list[dict]:
    if not song_title.strip():
        return []
    saved_at = datetime.now(UTC).isoformat()
    key = _conversation_key(song_title, artist)
    clean_question = question.strip()
    clean_answer = answer.strip()
    clean_turn_id = turn_id.strip() if turn_id else None
    with _lock:
        state = load_state()
        conversations = dict(state.get("listening_conversations", {}))
        existing = conversations.get(key, {})
        messages = list(existing.get("messages", []))
        if clean_turn_id and any(message.get("turn_id") == clean_turn_id for message in messages):
            return messages[-50:]
        if len(messages) >= 2 and messages[-2].get("role") == "user" and messages[-1].get("role") == "agent":
            if messages[-2].get("content") == clean_question and messages[-1].get("content") == clean_answer:
                return messages[-50:]
        messages.extend([
            {"role": "user", "content": clean_question, "saved_at": saved_at, "turn_id": clean_turn_id},
            {"role": "agent", "content": clean_answer, "saved_at": saved_at, "turn_id": clean_turn_id},
        ])
        conversations[key] = {
            "song_title": song_title,
            "artist": artist,
            "updated_at": saved_at,
            "messages": messages[-50:],
        }
        if len(conversations) > 100:
            newest = sorted(conversations.items(), key=lambda item: item[1].get("updated_at", ""), reverse=True)[:100]
            conversations = dict(newest)
        state["listening_conversations"] = conversations
        _write_state(state)
    return messages[-50:]


def favorite_recordings() -> list[dict]:
    state = load_state()
    store = get_store()
    timestamps = dict(state.get("favorite_timestamps", {}))
    for event in state["events"]:
        if event.get("action") in {"like", "save"} and event.get("recording_id"):
            timestamps.setdefault(event["recording_id"], event.get("at"))
    favorite_ids = list(dict.fromkeys([*state["liked"], *state["saved"]]))
    favorites = []
    for recording_id in favorite_ids:
        recording = store.get_recording(recording_id)
        if not recording:
            continue
        artist = store.get_artist(recording.artist_id)
        favorites.append({
            "recording_id": recording.id,
            "title": recording.title,
            "artist": artist.name if artist else "未知歌手",
            "saved_at": timestamps.get(recording_id),
            "liked": recording_id in state["liked"],
            "saved": recording_id in state["saved"],
        })
    return sorted(favorites, key=lambda item: item["saved_at"] or "", reverse=True)


def load_state() -> dict:
    if not STATE_PATH.exists():
        return _empty()
    try:
        return {**_empty(), **json.loads(STATE_PATH.read_text(encoding="utf-8"))}
    except (OSError, json.JSONDecodeError):
        return _empty()


def record_feedback(request: FeedbackRequest) -> dict:
    with _lock:
        state = load_state()
        event = {
            "recording_id": request.recording_id,
            "action": request.action,
            "channel": request.channel,
            "at": datetime.now(UTC).isoformat(),
        }
        if request.listened_seconds is not None:
            event["listened_seconds"] = round(request.listened_seconds, 1)
        state["events"] = [*state["events"][-499:], event]
        if request.action in {"like", "save"}:
            key = "liked" if request.action == "like" else "saved"
            state[key] = list(dict.fromkeys([*state[key], request.recording_id]))
            state["favorite_timestamps"].setdefault(request.recording_id, event["at"])
        if request.action == "like":
            state["like_counts"][request.recording_id] = int(state["like_counts"].get(request.recording_id, 0)) + 1
        if request.action == "skip":
            state["skipped"] = list(dict.fromkeys([*state["skipped"][-99:], request.recording_id]))
        if request.action in {"play", "replay"}:
            state["play_counts"][request.recording_id] = int(state["play_counts"].get(request.recording_id, 0)) + 1
        _write_state(state)
    return listener_summary(state)


def record_daily_listening(
    recording_id: str,
    title: str,
    artist: str | None,
    listened_seconds: float,
    listened_at: datetime | None = None,
) -> None:
    record_daily_listening_sqlite(
        recording_id,
        title,
        artist,
        listened_seconds,
        listened_at,
    )


def today_listening_stats(now: datetime | None = None) -> dict:
    return today_listening_stats_sqlite(now)


def record_recommendation_exposure(recording_ids: list[str], mode: str = "auto") -> None:
    shown_on = datetime.now().astimezone().date().isoformat()
    with _lock:
        state = load_state()
        existing = {
            (event.get("recording_id"), event.get("shown_on"), event.get("mode"))
            for event in state["events"]
            if event.get("action") == "exposure"
        }
        events = list(state["events"])
        for recording_id in recording_ids:
            key = (recording_id, shown_on, mode)
            if key in existing:
                continue
            events.append({
                "recording_id": recording_id,
                "action": "exposure",
                "channel": "today",
                "mode": mode,
                "shown_on": shown_on,
                "at": datetime.now(UTC).isoformat(),
            })
        state["events"] = events[-500:]
        _write_state(state)


def recent_recording_ids(days: int = 30) -> set[str]:
    cutoff = datetime.now(UTC) - timedelta(days=days)
    result = set()
    for event in load_state()["events"]:
        try:
            if datetime.fromisoformat(event["at"]) >= cutoff and event["action"] in {"play", "replay"}:
                result.add(event["recording_id"])
        except (KeyError, ValueError, TypeError):
            continue
    return result


def recent_exposed_recording_ids(days: int = 14) -> set[str]:
    today = datetime.now().astimezone().date()
    cutoff = today - timedelta(days=days)
    result = set()
    for event in load_state()["events"]:
        if event.get("action") != "exposure":
            continue
        try:
            shown_on = datetime.fromisoformat(event["shown_on"]).date()
            if cutoff <= shown_on < today:
                result.add(event["recording_id"])
        except (KeyError, ValueError, TypeError):
            continue
    return result


def _listening_period(value: str | None) -> str | None:
    if not value:
        return None
    try:
        observed_at = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone()
    except (TypeError, ValueError):
        return None
    if observed_at.hour < 6:
        return "\u6df1\u591c"
    if observed_at.hour < 11:
        return "\u4e0a\u5348"
    if observed_at.hour < 14:
        return "\u4e2d\u5348"
    if observed_at.hour < 18:
        return "\u4e0b\u5348"
    if observed_at.hour < 23:
        return "\u665a\u4e0a"
    return "\u6df1\u591c"


def _ranked_scores(scores: Counter, limit: int = 8) -> list[dict]:
    return [
        {"name": name, "score": round(float(score), 2)}
        for name, score in scores.most_common(limit)
        if score > 0
    ]


def _is_meaningful_preference_label(value: str) -> bool:
    normalized = value.strip().casefold()
    internal_labels = {
        "catalog",
        "discovery",
        "familiar",
        "imported",
        "itunes",
        "musicbrainz",
        "open-data",
        "seed",
        "user-library",
    }
    return bool(normalized) and normalized not in internal_labels and not normalized.startswith(
        ("catalog:", "source:")
    )


def listener_preference_profile(state: dict | None = None) -> dict:
    state = state or load_state()
    store = get_store()
    track_stats: dict[str, dict] = defaultdict(
        lambda: {
            "plays": 0,
            "replays": 0,
            "likes": 0,
            "saves": 0,
            "skips": 0,
            "seconds": 0.0,
        }
    )
    period_scores: Counter = Counter()
    listened_seconds = []

    for recording_id, count in state.get("play_counts", {}).items():
        track_stats[recording_id]["plays"] = int(count)

    for event in state.get("events", []):
        recording_id = event.get("recording_id")
        action = event.get("action")
        if not recording_id or action == "exposure":
            continue
        stats = track_stats[recording_id]
        if action == "replay":
            stats["replays"] += 1
        elif action == "skip":
            stats["skips"] += 1
        seconds = float(event.get("listened_seconds") or 0)
        if seconds:
            stats["seconds"] += seconds
            listened_seconds.append(seconds)
        if action in {"play", "replay"}:
            period = _listening_period(event.get("at"))
            if period:
                period_scores[period] += 1

    for recording_id in state.get("liked", []):
        track_stats[recording_id]["likes"] = max(1, int(state.get("like_counts", {}).get(recording_id, 0)))
    for recording_id in state.get("saved", []):
        track_stats[recording_id]["saves"] = 1

    artist_stats: dict[str, dict] = defaultdict(
        lambda: {
            "score": 0.0,
            "plays": 0,
            "replays": 0,
            "likes": 0,
            "saves": 0,
            "skips": 0,
        }
    )
    tag_scores: Counter = Counter()
    mood_scores: Counter = Counter()
    era_scores: Counter = Counter()
    top_tracks = []
    known_recordings = 0

    for recording_id, stats in track_stats.items():
        recording = store.get_recording(recording_id)
        if not recording:
            continue
        known_recordings += 1
        score = (
            stats["plays"]
            + stats["replays"] * 1.5
            + stats["likes"] * 4
            + stats["saves"] * 3
            - stats["skips"] * 2
            + min(stats["seconds"] / 240, 1.5)
        )
        artist = store.get_artist(recording.artist_id)
        artist_name = artist.name if artist else "\u672a\u77e5\u6b4c\u624b"
        artist_item = artist_stats[recording.artist_id]
        artist_item["name"] = artist_name
        artist_item["score"] += score
        for key in ("plays", "replays", "likes", "saves", "skips"):
            artist_item[key] += stats[key]
        positive_score = max(0.2, score)
        for tag in recording.tags:
            if _is_meaningful_preference_label(tag):
                tag_scores[tag] += positive_score
        for mood in recording.moods:
            if _is_meaningful_preference_label(mood):
                mood_scores[mood] += positive_score
        if recording.year:
            era_scores[f"{recording.year // 10 * 10}\u5e74\u4ee3"] += positive_score
        top_tracks.append({
            "recording_id": recording.id,
            "title": recording.title,
            "artist": artist_name,
            "score": round(score, 2),
            **stats,
        })

    top_artists = sorted(
        ({"artist_id": artist_id, **stats} for artist_id, stats in artist_stats.items()),
        key=lambda item: (-item["score"], -item["plays"], item["name"]),
    )[:8]
    top_tracks.sort(key=lambda item: (-item["score"], -item["plays"], item["title"]))
    play_actions = sum(
        1 for event in state.get("events", []) if event.get("action") in {"play", "replay"}
    )
    replay_actions = sum(
        1 for event in state.get("events", []) if event.get("action") == "replay"
    )
    skip_actions = sum(
        1 for event in state.get("events", []) if event.get("action") == "skip"
    )
    evidence_count = (
        play_actions
        + sum(int(value) for value in state.get("like_counts", {}).values())
        + len(state.get("liked", [])) * 2
        + len(state.get("saved", [])) * 2
        + len(state.get("music_notes", []))
        + len(state.get("lyric_fragments", []))
    )
    confidence = "high" if evidence_count >= 30 else "medium" if evidence_count >= 8 else "low"
    top_artist_names = [item["name"] for item in top_artists[:3]]
    top_tag_names = [item["name"] for item in _ranked_scores(tag_scores, 3)]
    separator = "\u3001"
    if top_artist_names or top_tag_names:
        summary = "\u4f60\u7684\u957f\u671f\u504f\u597d\u6b63\u5728\u5f62\u6210"
        if top_artist_names:
            summary += f"\uff1a\u5e38\u542c\u6b4c\u624b\u5305\u62ec{separator.join(top_artist_names)}"
        if top_tag_names:
            summary += f"\uff0c\u98ce\u683c\u66f4\u9760\u8fd1{separator.join(top_tag_names)}"
        summary += "\u3002"
    else:
        summary = (
            "\u76ee\u524d\u8bc1\u636e\u8fd8\u5c11\uff0c\u7cfb\u7edf\u6b63\u5728\u901a\u8fc7\u64ad\u653e\u3001\u6536\u85cf\u4e0e\u7b14\u8bb0"
            "\u5b66\u4e60\u4f60\u7684\u504f\u597d\u3002"
        )

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "confidence": confidence,
        "summary": summary,
        "top_artists": top_artists,
        "top_tracks": top_tracks[:10],
        "top_tags": _ranked_scores(tag_scores),
        "top_moods": _ranked_scores(mood_scores),
        "favorite_eras": _ranked_scores(era_scores, 5),
        "listening_periods": _ranked_scores(period_scores, 5),
        "behavior": {
            "play_actions": play_actions,
            "replay_actions": replay_actions,
            "skip_actions": skip_actions,
            "like_actions": sum(int(value) for value in state.get("like_counts", {}).values()),
            "replay_rate": round(replay_actions / max(1, play_actions), 3),
            "skip_rate": round(skip_actions / max(1, play_actions + skip_actions), 3),
            "average_listened_seconds": round(
                sum(listened_seconds) / max(1, len(listened_seconds)), 1
            ),
            "liked_count": len(state.get("liked", [])),
            "saved_count": len(state.get("saved", [])),
            "music_note_count": len(state.get("music_notes", [])),
            "lyric_fragment_count": len(state.get("lyric_fragments", [])),
        },
        "reflective_memory": {
            "recent_note_subjects": [
                {
                    "song_title": note.get("song_title"),
                    "artist": note.get("artist"),
                    "prompt": note.get("prompt"),
                }
                for note in state.get("music_notes", [])[:8]
            ],
            "recent_lyric_subjects": [
                {
                    "song_title": item.get("song_title"),
                    "artist": item.get("artist"),
                    "note": item.get("note"),
                }
                for item in state.get("lyric_fragments", [])[:8]
            ],
        },
        "evidence": {
            "event_count": len(state.get("events", [])),
            "known_recordings": known_recordings,
            "preference_signal_count": evidence_count,
        },
    }


def listener_summary(state: dict | None = None) -> dict:
    state = state or load_state()
    store = get_store()
    favorite_artists: dict[str, int] = {}
    top_recordings = []
    for recording_id, count in state["play_counts"].items():
        recording = store.get_recording(recording_id)
        if recording:
            favorite_artists[recording.artist_id] = favorite_artists.get(recording.artist_id, 0) + int(count)
            artist = store.get_artist(recording.artist_id)
            top_recordings.append({
                "recording_id": recording_id,
                "title": recording.title,
                "artist": artist.name if artist else "未知歌手",
                "play_count": int(count),
            })
    top_recordings.sort(key=lambda item: (-item["play_count"], item["title"]))
    recent_plays = []
    for event in reversed(state["events"]):
        if event.get("action") not in {"play", "replay"}:
            continue
        recording = store.get_recording(event.get("recording_id", ""))
        if not recording:
            continue
        artist = store.get_artist(recording.artist_id)
        recent_plays.append({
            "recording_id": recording.id,
            "title": recording.title,
            "artist": artist.name if artist else "未知歌手",
            "channel": event.get("channel", "unknown"),
            "at": event.get("at"),
        })
        if len(recent_plays) >= 12:
            break
    favorite_artist_ids = [item[0] for item in sorted(favorite_artists.items(), key=lambda pair: pair[1], reverse=True)[:5]]
    favorite_artist = store.get_artist(favorite_artist_ids[0]).name if favorite_artist_ids and store.get_artist(favorite_artist_ids[0]) else "尚未形成"
    total_play_count = sum(int(value) for value in state["play_counts"].values())
    return {
        "event_count": len(state["events"]), "liked_count": len(state["liked"]), "saved_count": len(state["saved"]),
        "like_actions": sum(int(value) for value in state.get("like_counts", {}).values()),
        "total_play_count": total_play_count,
        "top_recordings": top_recordings[:10],
        "recent_plays": recent_plays,
        "favorite_artist_ids": favorite_artist_ids,
        "listener_type": "沉浸式听众" if total_play_count >= 10 else "正在形成品味",
        "favorite_artist": favorite_artist,
        "preference_profile": listener_preference_profile(state),
    }
