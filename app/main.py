import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from .config import settings
from .events import append_event, read_events


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.event_log_path.parent.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(title="Gate Nine", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "gate-nine"}


@app.get("/api/events")
def events() -> list[dict]:
    return read_events(settings.event_log_path)


@app.post("/api/events")
def create_event(test_id: str, action: str) -> dict:
    return append_event(settings.event_log_path, test_id=test_id, action=action)


@app.get("/", response_class=HTMLResponse)
def dashboard() -> str:
    return """<!doctype html>
<html><head><title>Rachis tester</title></head>
<body><h1>Gate Nine</h1>
<p>Human-supervised test harness is running.</p>
<p><a href='/health'>Health</a> · <a href='/api/events'>Events</a></p>
</body></html>"""


def run() -> None:
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=False)

