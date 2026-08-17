from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
CATALOGS = [
    ROOT / "data" / "open_catalog.json",
    ROOT / "data" / "musicbrainz_discovery.json",
    ROOT / "data" / "itunes_catalog.json",
]


def is_fresh(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        generated_at = datetime.fromisoformat(payload["generated_at"])
        return generated_at >= datetime.now(UTC) - timedelta(days=1)
    except (KeyError, OSError, ValueError, json.JSONDecodeError):
        return False


def run() -> None:
    if all(is_fresh(path) for path in CATALOGS):
        return
    subprocess.run([sys.executable, str(ROOT / "scripts" / "build_itunes_catalog.py")], check=False)
    subprocess.run([sys.executable, str(ROOT / "scripts" / "build_open_catalog.py"), "--limit-per-artist", "24"], check=False)
    subprocess.run([
        sys.executable,
        str(ROOT / "scripts" / "build_musicbrainz_discovery.py"),
        "--target",
        "9000",
        "--pages-per-query",
        "3",
    ], check=False)
    try:
        httpx.post("http://127.0.0.1:8001/api/catalog/reload", timeout=8.0)
    except httpx.HTTPError:
        pass


if __name__ == "__main__":
    run()
