import tempfile
import unittest
from pathlib import Path

from app.events import append_event, read_events


class EventLogTests(unittest.TestCase):
    def test_events_are_append_only_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.jsonl"
            append_event(path, action="open_url", details={"url": "https://example.test"})
            append_event(path, action="capture_screenshot")

            self.assertEqual(len(read_events(path)), 2)
            self.assertEqual(read_events(path)[0]["action"], "open_url")
            self.assertNotIn("test_id", read_events(path)[0])


if __name__ == "__main__":
    unittest.main()

