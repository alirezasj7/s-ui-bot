"""PG overview node cards + live aggregate rates; ACL & sanitization."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class FormatBytesRateTests(unittest.TestCase):
    def test_rate_suffix(self):
        from app.services.formatting import format_bytes_rate, format_bytes_rate_parts

        self.assertEqual(format_bytes_rate(None), "—")
        self.assertIn("/ثانیه", format_bytes_rate(1024))
        self.assertNotEqual(format_bytes_rate(0), "نامحدود")
        num, unit = format_bytes_rate_parts(1024)
        self.assertEqual(num, "1")
        self.assertEqual(unit, "کیلوبایت/ثانیه")
        self.assertEqual(format_bytes_rate_parts(None), ("—", ""))


class NodeOverviewBuilderTests(unittest.TestCase):
    def test_realtime_cpu_ram_and_speeds(self):
        from app.services.node_traffic import build_nodes_overview, nodes_overview_json

        nodes = [
            {"id": 1, "name": "de-1", "status": "connected", "uplink": 1000, "downlink": 2000},
            {"id": 2, "name": "tr-1", "status": "connected", "uplink": 500, "downlink": 700},
        ]
        rt = {
            "1": {
                "cpu_usage": 41.2,
                "cpu_cores": 4,
                "mem_used": 2 * 1024**3,
                "mem_total": 8 * 1024**3,
                "incoming_bandwidth_speed": 111,
                "outgoing_bandwidth_speed": 222,
            },
            "2": {
                "cpu_usage": 10,
                "mem_used": 1 * 1024**3,
                "mem_total": 4 * 1024**3,
                "incoming_bandwidth_speed": 10,
                "outgoing_bandwidth_speed": 20,
            },
            "3": None,  # disconnected / missing
        }
        ov = build_nodes_overview(nodes, rt)
        self.assertEqual(len(ov["nodes"]), 2)
        n1 = ov["nodes"][0]
        self.assertEqual(n1["cpu_percent"], 41.2)
        self.assertEqual(n1["cpu_cores_text"], "4 هسته")
        self.assertEqual(n1["cpu_cores_parts"]["num"], "4")
        self.assertEqual(n1["cpu_cores_parts"]["unit"], "هسته")
        self.assertAlmostEqual(n1["mem_percent"], 25.0, places=0)
        self.assertEqual(n1["mem_parts"]["used"], "2.0")
        self.assertEqual(n1["mem_parts"]["total"], "8.0")
        self.assertEqual(n1["mem_parts"]["unit"], "گیگ")
        self.assertEqual(n1["status_kind"], "ok")
        self.assertEqual(ov["live"]["rate_up"], 242)
        self.assertEqual(ov["live"]["rate_down"], 121)
        self.assertIn("/ثانیه", ov["live"]["rate_up_text"])
        self.assertTrue(ov["live"]["rate_up_num"])
        self.assertIn("/ثانیه", ov["live"]["rate_up_unit"])
        self.assertEqual(n1["rate_up_parts"]["num"], ov["nodes"][0]["rate_up_parts"]["num"])

        payload = nodes_overview_json(ov)
        self.assertIn("live", payload)
        self.assertIn("nodes", payload)
        self.assertIn("rate_up_num", payload["live"])
        self.assertIn("rate_up_parts", payload["nodes"][0])
        self.assertIn("cpu_cores_text", payload["nodes"][0])
        self.assertEqual(payload["nodes"][0]["cpu_cores_parts"]["num"], "4")
        self.assertEqual(payload["nodes"][0]["mem_parts"]["unit"], "گیگ")
        # No raw secrets / unrelated keys
        dumped = str(payload)
        self.assertNotIn("server_ca", dumped)
        self.assertNotIn("api_key", dumped)
        self.assertNotIn("mem_used", dumped)  # absolute bytes not in poll JSON
        self.assertEqual(payload["nodes"][0]["traffic_up"]["num"], n1["traffic_up"]["num"])

    def test_missing_realtime_shows_dashes(self):
        from app.services.node_traffic import build_nodes_overview

        ov = build_nodes_overview([{"id": 9, "name": "x", "status": "disabled"}], None)
        card = ov["nodes"][0]
        self.assertEqual(card["cpu_text"], "—")
        self.assertEqual(card["mem_text"], "—")
        self.assertEqual(card["rate_up_text"], "—")
        self.assertEqual(card["rate_up_parts"]["num"], "—")
        self.assertEqual(card["status_kind"], "err")
        self.assertIsNone(ov["live"]["rate_up"])

    def test_enrich_still_supports_nodes_page(self):
        from app.services.node_traffic import enrich_nodes_with_traffic

        out = enrich_nodes_with_traffic(
            [{"id": 7, "name": "x"}],
            {"nodes": [{"node_id": 7, "upload": 10, "download": 20}]},
        )
        self.assertEqual(out[0]["_traffic_total"], 30)


class PgOverviewSurfaceTests(unittest.TestCase):
    def test_css_node_board(self):
        css = (ROOT / "app/web/static/panel.css").read_text(encoding="utf-8")
        self.assertIn(".pg-node-tile", css)
        tile = css.split(".pg-node-tile {\n", 1)[1].split("}", 1)[0]
        period = css.split(".home-period {\n", 1)[1].split("}", 1)[0]
        self.assertIn("background: rgba(255, 255, 255, 0.03);", tile)
        self.assertIn("border: 1px solid var(--border);", tile)
        self.assertIn("background: rgba(255, 255, 255, 0.03);", period)
        light = css.split('html[data-theme="light"] .pg-node-tile {\n', 1)[1].split("}", 1)[0]
        light_period = css.split('html[data-theme="light"] .home-period {\n', 1)[1].split("}", 1)[0]
        self.assertIn("background: rgba(0, 0, 0, 0.02);", light)
        self.assertIn("background: rgba(0, 0, 0, 0.02);", light_period)
        self.assertIn(".pg-live-rates", css)
        self.assertIn(".pg-metric-unit", css)
        self.assertIn(".pg-metric-val-rate", css)
        rate_block = css[css.find(".pg-metric-val-rate") : css.find(".pg-metric-val-rate") + 1200]
        self.assertIn("direction: rtl", rate_block)
        self.assertNotIn("row-reverse", rate_block)
        self.assertIn(".pg-node-metric .pg-metric-val-rate", css)
        meta_block = css[css.find(".pg-node-metric-meta") : css.find(".pg-node-metric-meta") + 900]
        self.assertIn("direction: rtl", meta_block)
        self.assertNotIn("direction: ltr", meta_block.split("{", 1)[1].split("}", 1)[0])
        self.assertIn(".pg-node-meter", css)
        self.assertIn(".pg-node-tabs", css)
        self.assertIn(".pg-node-metric-res", css)
        # Percent label has no chip box
        start = css.find(".pg-node-meter-pct")
        body = css[start : start + 450].split("{", 1)[1].split("}", 1)[0]
        self.assertIn("text-shadow: none", body)
        self.assertIn(".pg-node-meter-pct-on-fill", css)

    def test_metrics_route_fetches_nodes_and_owner_guard(self):
        src = (ROOT / "app/api/pg_pages.py").read_text(encoding="utf-8")
        chunk = src.split("async def pg_host_metrics_json")[1][:1200]
        self.assertIn("_is_pg_owner_principal(staff)", chunk)
        self.assertIn("status_code=403", chunk)
        self.assertIn("get_nodes_realtime", chunk)
        self.assertIn("nodes_overview_json", chunk)
        self.assertIn("build_nodes_overview", chunk)


if __name__ == "__main__":
    unittest.main()
