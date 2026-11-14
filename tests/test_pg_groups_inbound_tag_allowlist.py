"""Regression test: /pg/groups create & edit must not trust raw inbound tags.

Before the fix, ``pg_groups_create``/``pg_groups_edit`` forwarded every
``tag_*`` form field straight to PasarGuard's ``create_group``/``modify_group``
as ``inbound_tags`` with no validation against the admin's own inbounds. A
crafted POST could reference inbound tags the caller was never shown (e.g.
tags belonging to a different node/scope), so PasarGuard — not this app —
was the only thing standing between the request and an out-of-scope inbound
being wired into a group. Now every submitted tag must appear in
``pg.get_inbounds()`` for that same admin, or it is silently dropped.
"""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock

from fastapi import FastAPI


def _find_route(app: FastAPI, path: str, method: str):
    for route in app.routes:
        if getattr(route, "path", None) == path and method.upper() in (
            getattr(route, "methods", None) or set()
        ):
            return route
    raise AssertionError(f"route not found: {method} {path}")


class _FakeRequest:
    def __init__(self, form_data: dict):
        self._form_data = form_data

    async def form(self):
        return self._form_data


class PgGroupsInboundTagAllowlistTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        from app.api import pg_pages

        self.app = FastAPI()
        pg_pages.register_pg_pages(
            self.app,
            render=lambda *a, **k: None,
            require_pg_perm=lambda perm: (lambda: None),
            get_db=lambda: None,
        )
        self.create_route = _find_route(self.app, "/pg/groups", "POST")
        self.edit_route = _find_route(self.app, "/pg/groups/{group_id}/edit", "POST")

        self.staff = {"role": "admin", "id": 1, "username": "root"}
        self.fake_pg = AsyncMock()
        self.fake_pg.get_inbounds = AsyncMock(return_value=["vless-real", "vmess-real"])
        self.fake_pg.create_group = AsyncMock(return_value={"id": 1})
        self.fake_pg.modify_group = AsyncMock(return_value={"id": 1})

        self._patches = [
            unittest.mock.patch("app.api.pg_pages.staff_pg_action", return_value=True),
            unittest.mock.patch(
                "app.api.pg_pages.assert_can_mutate_owned_users", new=AsyncMock()
            ),
            unittest.mock.patch(
                "app.api.pg_pages._staff_pg",
                new=AsyncMock(return_value=(self.fake_pg, False)),
            ),
        ]
        for p in self._patches:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in self._patches])

    async def test_create_group_drops_unknown_tags(self):
        request = _FakeRequest({"tag_0": "vless-real", "tag_1": "spoofed-tag"})
        resp = await self.create_route.endpoint(
            request=request, name="Team", staff=self.staff, session=None
        )
        self.assertEqual(resp.status_code, 303)
        self.fake_pg.create_group.assert_awaited_once()
        payload = self.fake_pg.create_group.await_args.args[0]
        self.assertEqual(payload["inbound_tags"], ["vless-real"])
        self.assertNotIn("spoofed-tag", payload["inbound_tags"])

    async def test_create_group_rejects_when_all_tags_unknown(self):
        request = _FakeRequest({"tag_0": "totally-fake"})
        resp = await self.create_route.endpoint(
            request=request, name="Team", staff=self.staff, session=None
        )
        self.assertEqual(resp.status_code, 303)
        self.assertIn("err=", resp.headers["location"])
        self.fake_pg.create_group.assert_not_awaited()

    async def test_create_group_keeps_all_valid_tags(self):
        request = _FakeRequest({"tag_0": "vless-real", "tag_1": "vmess-real"})
        await self.create_route.endpoint(
            request=request, name="Team", staff=self.staff, session=None
        )
        payload = self.fake_pg.create_group.await_args.args[0]
        self.assertCountEqual(payload["inbound_tags"], ["vless-real", "vmess-real"])

    async def test_edit_group_drops_unknown_tags(self):
        request = _FakeRequest({"tag_0": "vmess-real", "tag_1": "spoofed-tag"})
        resp = await self.edit_route.endpoint(
            request=request, group_id=1, name="Team", staff=self.staff, session=None
        )
        self.assertEqual(resp.status_code, 303)
        self.fake_pg.modify_group.assert_awaited_once()
        args = self.fake_pg.modify_group.await_args.args
        self.assertEqual(args[0], 1)
        self.assertEqual(args[1]["inbound_tags"], ["vmess-real"])


if __name__ == "__main__":
    unittest.main()
