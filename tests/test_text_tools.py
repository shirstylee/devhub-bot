import base64
import hashlib
import unittest

from bot.services.text_tools import TextToolError, transform_text


class TextToolsTests(unittest.TestCase):
    def test_base64_round_trip_keeps_unicode(self) -> None:
        source = "DevHub — Привет"
        encoded = transform_text("base64_encode", source)
        self.assertEqual(encoded, base64.b64encode(source.encode()).decode())
        self.assertEqual(transform_text("base64_decode", encoded), source)

    def test_invalid_base64_is_rejected(self) -> None:
        with self.assertRaisesRegex(TextToolError, "invalid_base64"):
            transform_text("base64_decode", "not base64!")

    def test_url_and_hash_operations(self) -> None:
        source = "hello world/тест"
        encoded = transform_text("url_encode", source)
        self.assertEqual(transform_text("url_decode", encoded), source)
        self.assertEqual(transform_text("sha256", source), hashlib.sha256(source.encode()).hexdigest())
        self.assertEqual(transform_text("sha512", source), hashlib.sha512(source.encode()).hexdigest())


if __name__ == "__main__":
    unittest.main()
