"""Save/load utilities for game state persistence."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

SAVES_DIR = Path("saves")


def _ensure_saves_dir() -> None:
    SAVES_DIR.mkdir(exist_ok=True)


def save_game(state: dict[str, Any], slot: str = "slot1") -> str:
    """Serialize GameState to a JSON file. Returns save path."""
    _ensure_saves_dir()
    state_copy = dict(state)
    state_copy["real_datetime"] = datetime.now().isoformat()
    state_copy["save_slot"] = slot
    path = SAVES_DIR / f"{slot}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state_copy, f, ensure_ascii=False, indent=2)
    return str(path)


def load_game(slot: str = "slot1") -> dict[str, Any] | None:
    """Load GameState from a JSON file. Returns None if not found."""
    path = SAVES_DIR / f"{slot}.json"
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def list_saves() -> list[dict[str, str]]:
    """List all available save slots with metadata."""
    _ensure_saves_dir()
    saves = []
    for p in sorted(SAVES_DIR.glob("*.json")):
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            saves.append({
                "slot": p.stem,
                "story_time": data.get("story_time", "未知"),
                "turn_count": str(data.get("turn_count", 0)),
                "real_datetime": data.get("real_datetime", "未知"),
                "scene": data.get("scene", "")[:30],
            })
        except Exception:
            continue
    return saves


def delete_save(slot: str) -> bool:
    """Delete a save slot. Returns True if deleted."""
    path = SAVES_DIR / f"{slot}.json"
    if path.exists():
        os.remove(path)
        return True
    return False
