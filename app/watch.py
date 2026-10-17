"""Print new log lines to the terminal as they land.

    uv run python -m app.watch

Run this in a second terminal while app.driver runs the plan. It prints every
new event the driver appends, so the human can follow what is happening in the
terminal instead of only watching the browser window.

Polls the log file for growth rather than blocking on a watch call, so a run
started before this watcher is picked up cleanly.
"""

import json
import time

from .config import settings

POLL_SECONDS = 0.4


def format_event(event: dict) -> str:
    """One line for the terminal: what happened, and to which step."""
    stamp = str(event.get("timestamp", ""))[:19].replace("T", " ")
    action = event.get("action", "")
    details = event.get("details") or {}
    subject = " ".join(str(value) for value in details.values() if value != "")
    return f"{stamp}  {action:<24} {subject}".rstrip()


def watch() -> None:
    """Follow the event log from the top, printing each new line."""
    path = settings.event_log_path
    print(f"following {path}", flush=True)
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                print(format_event(_decode(line)), flush=True)
    offset = _offset()
    while True:
        if path.exists() and path.stat().st_size > offset:
            with path.open("r", encoding="utf-8") as stream:
                stream.seek(offset)
                for line in stream:
                    if line.strip():
                        print(format_event(_decode(line)), flush=True)
                offset = stream.tell()
        time.sleep(POLL_SECONDS)


def _offset() -> int:
    path = settings.event_log_path
    return path.stat().st_size if path.exists() else 0


def _decode(line: str) -> dict:
    try:
        return json.loads(line)
    except ValueError:
        return {"action": line.strip()}


if __name__ == "__main__":
    watch()
