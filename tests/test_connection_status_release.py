"""Update metadata advertises the release containing bot status buttons."""

from __future__ import annotations

import unittest
from pathlib import Path

from app.services.release_notes import changelog_for_update_page, latest_notes_block
from app.version import __version__


class StatusButtonReleaseTests(unittest.TestCase):
    def test_status_button_release_is_detectable_from_the_previous_version(self) -> None:
        self.assertGreaterEqual(tuple(map(int, __version__.split("."))), (0, 4, 6))
        self.assertEqual((Path(__file__).resolve().parents[1] / "VERSION").read_text().strip(), __version__)
        notes = latest_notes_block()
        self.assertEqual(notes["version"], __version__)
        self.assertTrue(notes["notes"])
        upgrade = changelog_for_update_page(local="0.4.5", remote="0.4.6")
        self.assertTrue(upgrade["has_notes"])
        self.assertEqual([block["version"] for block in upgrade["blocks"]], ["0.4.6"])
