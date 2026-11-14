"""Host gauges moved to bot/PG overviews; ACL + table column classes."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


ROOT = Path(__file__).resolve().parents[1]


class HostGaugesUnitTests(unittest.TestCase):
    def test_from_pg_system_stats(self):
        from app.services.host_gauges import gauges_from_pg_system_stats

        g = gauges_from_pg_system_stats(
            {
                "cpu_usage": 42.5,
                "cpu_cores": 4,
                "mem_used": 2 * 1024**3,
                "mem_total": 8 * 1024**3,
                "version": "1.2.3",
                "disk_total": 999,
            }
        )
        self.assertTrue(g["ok"])
        self.assertEqual(g["cpu_percent"], 42.5)
        self.assertEqual(g["cpu_cores"], 4)
        self.assertAlmostEqual(g["memory_percent"], 25.0, places=0)
        self.assertEqual(g["cpu_tone"], "ok")
        # Only CPU/RAM — unrelated keys must not appear
        self.assertNotIn("version", g)
        self.assertNotIn("disk_total", g)

    def test_local_host_gauges_shape(self):
        from app.services.host_gauges import gauges_json, local_host_gauges

        g = local_host_gauges(wait_cpu=0.05)
        payload = gauges_json(g)
        for key in ("cpu_percent", "memory_percent", "cpu_tone", "mem_tone", "memory_ratio_text"):
            self.assertIn(key, payload)


class OverviewSurfaceTests(unittest.TestCase):
    def test_home_has_no_gauges_or_metrics_poll(self):
        home = (ROOT / "app/web/templates/_home_dash_body.html").read_text(encoding="utf-8")
        self.assertNotIn("home-gauge", home)
        self.assertNotIn("/home/metrics", home)
        self.assertIn("status_tiles", home)

    def test_build_home_overview_skips_host_metrics(self):
        src = (ROOT / "app/services/home_overview.py").read_text(encoding="utf-8")
        self.assertIn("Host CPU/RAM live on bot/PG overviews", src)
        self.assertNotIn("metrics_task = asyncio.to_thread(host_metrics", src)

    def test_pg_metrics_route_owner_only(self):
        src = (ROOT / "app/api/pg_pages.py").read_text(encoding="utf-8")
        self.assertIn('@app.get("/pg/metrics")', src)
        self.assertIn("_is_pg_owner_principal(staff)", src)
        self.assertIn('status_code=403', src.split("async def pg_host_metrics_json")[1][:800])

    def test_colors_section_head_no_accent_box(self):
        html = (ROOT / "app/web/templates/_settings_colors.html").read_text(encoding="utf-8")
        css = (ROOT / "app/web/static/panel.css").read_text(encoding="utf-8")
        self.assertIn("btn-color-section-head", html)
        self.assertIn("btn-color-section-head", css)
        chunk = css[css.find("btn-color-section-head") : css.find("btn-color-section-head") + 1200]
        self.assertNotIn("border-inline-start", chunk)
        self.assertNotIn("ادمین · ", css)
        # Title↔caption unit matches .card (flex gap space-2 + pull space-1)
        self.assertIn("gap: var(--space-2)", chunk)
        self.assertIn("margin-top: calc(-1 * var(--space-1))", chunk)
        # Closer to cards BELOW; extra space-2 above form gap for clearer boundary
        self.assertIn("calc(var(--space-2) - var(--section-gap))", chunk)
        self.assertIn("margin: 0 0 calc(var(--space-2) - var(--section-gap))", chunk)
        self.assertIn(
            ".settings-card + .btn-color-section-head,\n.card + .btn-color-section-head {\n  margin-top: var(--space-2);",
            css,
        )

    def test_table_col_id_css_and_headers(self):
        css = (ROOT / "app/web/static/panel.css").read_text(encoding="utf-8")
        self.assertIn("th.col-id", css)
        self.assertIn("max-width: 4.5rem", css)
        finance = (ROOT / "app/web/templates/finance.html").read_text(encoding="utf-8")
        self.assertIn('class="col-id"', finance)
        nodes = (ROOT / "app/web/templates/pg_nodes.html").read_text(encoding="utf-8")
        self.assertIn('class="col-id"', nodes)
        self.assertIn("col-name", nodes)


class PgMetricsAclAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_gauges_from_stats_used_by_owner_path(self):
        from app.services.host_gauges import gauges_from_pg_system_stats

        # Reseller must not get raw system dumps via this helper's output shape
        g = gauges_from_pg_system_stats({"cpu_usage": 10, "secret_token": "x"})
        self.assertNotIn("secret_token", g)


if __name__ == "__main__":
    unittest.main()
