"""Send run events to a remote FastAPI endpoint over HTTP Basic Auth.

No local JSONL log is kept. Every event is POSTed to ``events_url`` using the
``anyuser:<password>`` Basic Auth credential (matching the working curl
equivalent). Only the password is validated by the remote.
"""

import base64
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any


def send_event(
    url: str,
    password: str,
    *,
    test_id: str,
    action: str,
    details: dict[str, Any] | None = None,
    retries: int = 2,
) -> bool:
    """POST one event to the remote endpoint over HTTP Basic Auth.

    Returns True when the remote accepted the event (HTTP 2xx). Never raises —
    a logging failure must not kill a browser run.
    """
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "test_id": test_id,
        "action": action,
        "details": details or {},
    }
    payload = json.dumps(event, ensure_ascii=False).encode("utf-8")
    # Match the working curl equivalent: -u "anyuser:<password>".
    # Only the password is validated by the remote.
    credential = f"anyuser:{password}"
    token = base64.b64encode(credential.encode("utf-8")).decode("ascii")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Basic {token}",
    }
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            request = urllib.request.Request(
                url, data=payload, headers=headers, method="POST"
            )
            with urllib.request.urlopen(request, timeout=10) as response:
                return 200 <= response.status < 300
        except (urllib.error.URLError, OSError) as exc:  # noqa: BLE001 - network
            last_error = exc
            time.sleep(0.5 * (attempt + 1))
    print(
        f"[events] could not send {action} for {test_id} to {url}: {last_error}",
        file=sys.stderr,
    )
    return False
