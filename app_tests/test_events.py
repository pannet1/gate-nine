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
                "alice",
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

    def test_send_event_returns_false_when_unreachable(self) -> None:
        with patch(
            "app.events.urllib.request.urlopen", side_effect=OSError("down")
        ):
            self.assertFalse(
                send_event(
                    "https://down.example/ingest",
                    "alice",
                    "secret",
                    test_id="1",
                    action="x",
                )
            )

    def test_send_event_uses_only_password_when_username_empty(self) -> None:
        """With no username, the Basic credential is just the password."""
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
            captured["headers"] = dict(request.header_items())
            return FakeResponse()

        import base64

        with patch("app.events.urllib.request.urlopen", side_effect=fake_open):
            send_event(
                "https://events.example/ingest",
                "",
                "admin-secret",
                test_id="001",
                action="sign_in",
            )

        auth = captured["headers"]["Authorization"]
        self.assertTrue(auth.startswith("Basic "))
        decoded = base64.b64decode(auth.split(" ", 1)[1]).decode("utf-8")
        self.assertEqual(decoded, "admin-secret")
        self.assertNotIn(":", decoded)


if __name__ == "__main__":
    unittest.main()
