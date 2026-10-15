"""Offline checks for utilities and the seat map's click fallback contract."""

import json
import logging
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock

from src.sites.kktix.map import SeatsMap
from src.sites.utils import centroid, parse_coords, safe_text
from src.utils.config_reader import ConfigReader


class GeometryTests(unittest.TestCase):
    def test_supported_shapes_and_degenerate_polygon(self):
        cases = {
            "10,20,5": (10, 20),
            "0,0,20,10": (10, 5),
            "0,0,6,0,0,6": (2, 2),
            "0,0,2,2,4,4": (2, 2),
        }
        for coords, expected in cases.items():
            with self.subTest(coords=coords):
                self.assertEqual(centroid(coords), expected)

    def test_coordinate_parsing_and_invalid_input(self):
        self.assertEqual(parse_coords(" -2,\n 4, 6 "), [-2, 4, 6])
        with self.assertRaises(ValueError):
            centroid("")


class ConfigReaderTests(unittest.TestCase):
    def test_cache_and_explicit_reload(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            try:
                path.write_text(json.dumps({"page": 1}), encoding="utf-8")
                reader = ConfigReader(path)
                self.assertIs(reader, ConfigReader(path))
                self.assertEqual(reader.load(), {"page": 1})
                path.write_text(json.dumps({"page": 2}), encoding="utf-8")
                self.assertEqual(reader.load(), {"page": 1})
                self.assertEqual(reader.load(reload=True), {"page": 2})
            finally:
                ConfigReader._instances.pop(path.resolve(), None)


class SafeTextTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_empty_and_failed_text_reads(self):
        locator = Mock(count=AsyncMock(return_value=0), text_content=AsyncMock())
        unit = Mock(locator=Mock(return_value=locator))
        self.assertEqual(await safe_text(unit, ".title"), "")
        locator.text_content.assert_not_awaited()
        locator.count.return_value = 1
        locator.text_content.return_value = "  title  "
        self.assertEqual(await safe_text(unit, ".title"), "title")
        locator.text_content.return_value = None
        self.assertEqual(await safe_text(unit, ".title"), "")
        locator.text_content.side_effect = RuntimeError("detached")
        self.assertEqual(await safe_text(unit, ".title"), "")


class SeatMapTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.calls = []
        self.native_click = True
        self.overlay_checks = []
        self.areas = [{"alt": "A區", "centroidViewport": {"x": 100, "y": 200}}]
        self.image = Mock(scroll_into_view_if_needed=AsyncMock())
        self.page = Mock(
            evaluate=AsyncMock(side_effect=self.evaluate),
            locator=Mock(return_value=self.image),
            mouse=Mock(click=AsyncMock()),
        )
        self.map = SeatsMap(
            self.page,
            {"js": {"extract": "EXTRACT"}, "selectors": {"img": "#map"}},
            logging.getLogger("test.seat_map"),
        )

    async def evaluate(self, script, *args):
        self.calls.append(script)
        if script == "EXTRACT":
            return {"areas": self.areas}
        if "a.click();" in script:
            return self.native_click
        if "el.closest(" in script:
            return self.overlay_checks.pop(0) if self.overlay_checks else True
        return None

    def assert_dom_restored(self):
        self.assertIn("delete b.dataset._pe", self.calls[-1])

    async def test_native_click_takes_precedence(self):
        self.assertIs(await self.map.click_section_by_alt(" A區 "), self.page)
        self.page.mouse.click.assert_not_awaited()
        self.image.scroll_into_view_if_needed.assert_awaited_once()
        self.assert_dom_restored()

    async def test_fallback_skips_overlay_and_uses_next_offset(self):
        self.native_click = False
        self.overlay_checks = [False, True]
        await self.map.click_section_by_alt("A區")
        self.page.mouse.click.assert_awaited_once_with(106, 200)
        self.assert_dom_restored()

    async def test_failed_mouse_click_retries_and_restores_dom(self):
        self.native_click = False
        self.page.mouse.click.side_effect = RuntimeError("click failed")
        self.assertIs(await self.map.click_section_by_alt("A區"), self.page)
        self.assertEqual(self.page.mouse.click.await_count, 13)
        self.assert_dom_restored()

    async def test_blank_or_unknown_section_does_not_click(self):
        await self.map.click_section_by_alt("")
        self.page.evaluate.assert_not_awaited()
        await self.map.click_section_by_alt("unknown")
        self.page.locator.assert_not_called()
        self.page.mouse.click.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
