"""Loads trading strategy files from the config folder."""

import json
from pathlib import Path
from typing import Any


STRATEGY_DIR = Path(__file__).resolve().parents[2] / "config" / "strategies"


def load_strategy(name: str) -> dict[str, Any]:
    """Loads a single strategy JSON file and returns it as a Python dict."""
    file_name = name if name.endswith(".json") else f"{name}.json"
    path = STRATEGY_DIR / file_name
    if not path.exists():
        raise FileNotFoundError(f"Strategy file not found: {path.name}")

    with path.open("r", encoding="utf-8") as handle:
        strategy = json.load(handle)

    strategy["file_name"] = path.name
    strategy["slug"] = path.stem
    return strategy


def list_strategies() -> list[dict[str, Any]]:
    """Returns a list of all available strategy files with lightweight metadata."""
    strategies: list[dict[str, Any]] = []
    for path in sorted(STRATEGY_DIR.glob("*.json")):
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        strategies.append(
            {
                "name": data.get("name", path.stem),
                "slug": path.stem,
                "instrument": data.get("instrument"),
                "session_start": data.get("session_start"),
                "session_end": data.get("session_end"),
            }
        )
    return strategies
