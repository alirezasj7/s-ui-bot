"""Isolated SQLite/PostgreSQL databases shared by monitor behavior tests."""

from __future__ import annotations

import os
import json
import secrets
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import Base
from app.db.models import BotUser, OrgPrincipal
from app.services.authz import authz_from_staff
from app.services.connection_monitor_access import MonitorAccess
from app.services.connection_monitor_subscription import subscription_entries


OWNER_STAFF = {
    "role": "admin", "org_principal_id": 1, "org_depth": 0,
    "org_parent_id": None, "org_status": "active",
}


def subscription_fixture_key(index: int = 0) -> str:
    fixture = json.loads((Path(__file__).parent / "fixtures/connection_monitor_catalog.json").read_text())
    return subscription_entries(fixture["native_configs"])[index].config_key


def monitor_access(**changes: object) -> MonitorAccess:
    return MonitorAccess(authz_from_staff({**OWNER_STAFF, **changes}), True)


class MonitorDatabaseCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="pgclock-monitor-tests-")
        self.admin_engine = None
        url = os.environ.get("PGCLOCK_CONNECTION_TEST_URL")
        if url:
            self.schema = "monitor_test_" + secrets.token_hex(8)
            self.admin_engine = create_async_engine(url)
            async with self.admin_engine.begin() as conn:
                await conn.execute(text(f'CREATE SCHEMA "{self.schema}"'))
            self.engine = create_async_engine(url, connect_args={"server_settings": {"search_path": self.schema}})
        else:
            self.engine = create_async_engine(f"sqlite+aiosqlite:///{Path(self.temporary.name) / 'monitor.db'}")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.Session = async_sessionmaker(self.engine, expire_on_commit=False)
        self.now = datetime.now(timezone.utc)
        self.access = monitor_access()
        async with self.Session() as session:
            session.add_all([
                BotUser(id=1, telegram_id=101, referral_code="owner", role="admin"),
                BotUser(id=2, telegram_id=102, referral_code="shop2", role="reseller"),
                BotUser(id=3, telegram_id=103, referral_code="shop3", role="reseller"),
                BotUser(id=4, telegram_id=104, referral_code="customer1", reseller_id=2),
                BotUser(id=5, telegram_id=105, referral_code="customer2", reseller_id=3),
                OrgPrincipal(id=1, depth=0, status="active"),
                OrgPrincipal(id=2, parent_id=1, depth=1, status="active"),
            ])
            await session.commit()

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()
        if self.admin_engine is not None:
            async with self.admin_engine.begin() as conn:
                await conn.execute(text(f'DROP SCHEMA "{self.schema}" CASCADE'))
            await self.admin_engine.dispose()
        self.temporary.cleanup()
