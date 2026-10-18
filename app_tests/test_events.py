import json
import unittest
from unittest.mock import MagicMock, patch

from app.events import send_event


class EventSendTests(unittest.TestCase):
    def test_send_event_posts_json_with_basic_auth(self) -> None:
        captured: dict = {}

        class FakeResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return b"{}"

        def fake_open(request, timeout=None):
            captured["method"] = request.method
            captured["url"] = request.full_url
            captured["headers"] = dict(request.header_items())
            captured["body"] = json.loads(request.data)
            return FakeResponse()

        with patch("app.events.urllib.request.urlopen", side_effect=fake_open):
            ok = send_event(
                "https://events.example/ingest",
                "secret",
                test_id="001",
                action="sign_in",
                details={"user": "alice"},
            )

        self.assertTrue(ok)
        self.assertEqual(captured["method"], "POST")
        self.assertEqual(captured["url"], "https://events.example/ingest")
        self.assertEqual(captured["body"]["test_id"], "001")
        self.assertEqual(captured["body"]["action"], "sign_in")
        self.assertEqual(captured["body"]["details"], {"user": "alice"})
        self.assertTrue(captured["body"]["timestamp"])
        self.assertIn("Authorization", captured["headers"])
        self.assertTrue(captured["headers"]["Authorization"].startswith("Basic "))
        import base64

        decoded = base64.b64decode(
            captured["headers"]["Authorization"].split(" ", 1)[1]
        ).decode("utf-8")
        self.assertEqual(decoded, "secret")

    def test_send_event_returns_false_when_unreachable(self) -> None:
        with patch(
            "app.events.urllib.request.urlopen", side_effect=OSError("down")
        ):
            self.assertFalse(
                send_event(
                    "https://down.example/ingest",
                    "secret",
                    test_id="1",
                    action="x",
                )
            )


if __name__ == "__main__":
    unittest.main()
