"""Settings captions stay short enough to read at a glance; long teaching belongs in the guide."""

from __future__ import annotations

import unittest

from app.services.users import SETTING_GROUPS

MAX_CAPTION_CHARS = 220


class SettingsCaptionLengthTests(unittest.TestCase):
    def test_no_settings_caption_is_longer_than_the_limit(self) -> None:
        too_long = [
            (field[0], len(field[3]))
            for fields in SETTING_GROUPS.values()
            for field in fields
            if len(field) > 3 and isinstance(field[3], str) and len(field[3]) > MAX_CAPTION_CHARS
        ]
        self.assertEqual(too_long, [])
