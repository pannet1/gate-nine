import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def append_event(path: Path, *, test_id: str, action: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "test_id": test_id,
        "action": action,
        "details": details or {},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(event, ensure_ascii=False) + "\n")
    return event


def read_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

