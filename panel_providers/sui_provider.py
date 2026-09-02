"""Provider for the alireza0/S-UI panel.

S-UI is a sing-box panel and is not API-compatible with 3X-UI.  Its external
API lives below ``/apiv2``, authenticates with the ``Token`` header and accepts
mutations through a form-encoded ``/save`` endpoint.
"""
from __future__ import annotations

import base64
import copy
import json
import secrets
import string
import time
import uuid

import aiohttp

from .base import BasePanelProvider, PanelError, PanelUserResult, PanelUsernameTakenError


_USER_INBOUND_TYPES = {
    "mixed", "socks", "http", "shadowsocks", "shadowtls", "vmess",
    "vless", "anytls", "trojan", "naive", "hysteria", "hysteria2", "tuic",
}


class SUIProvider(BasePanelProvider):
    """Manage S-UI clients through the token-authenticated REST API."""

    def _api_base_url(self) -> str:
        base = self.server["api_url"].rstrip("/")
        return base if base.endswith("/apiv2") else f"{base}/apiv2"

    def _session(self) -> aiohttp.ClientSession:
        connector = aiohttp.TCPConnector(ssl=False)
        return aiohttp.ClientSession(
            connector=connector,
            headers={
                # S-UI-X prefers Bearer; older S-UI builds use Token. Sending
                # both keeps the provider compatible across the 1.x line.
                "Authorization": f"Bearer {self.server['api_password']}",
                "Token": self.server["api_password"],
                "Accept": "application/json",
            },
            timeout=aiohttp.ClientTimeout(total=25),
        )

    async def _request_json(self, session: aiohttp.ClientSession, method: str, path: str,
                            *, operation: str, params=None, form=None):
        url = f"{self._api_base_url()}/{path.lstrip('/')}"
        try:
            async with session.request(method, url, params=params, data=form) as resp:
                text = await resp.text()
                final_url = str(resp.url)
                status = resp.status
                redirected_to_login = any("/login" in str(h.url) for h in resp.history) or "/login" in final_url
        except aiohttp.ClientError as exc:
            raise PanelError(f"خطا در اتصال به پنل S-UI: {exc}") from exc

        if status in (401, 403):
            raise PanelError(f"خطا در احراز هویت S-UI (کد {status}): API Token را بررسی کن.")
        if redirected_to_login:
            raise PanelError(
                "S-UI درخواست API را به صفحه ورود هدایت کرد؛ آدرس پنل باید شامل مسیر پایه "
                "(مثلاً http://server:2095/app) باشد و API Token معتبر باشد."
            )
        if status >= 400:
            raise PanelError(f"خطا در {operation} (کد {status}): {text[:300]}")
        try:
            payload = json.loads(text)
        except (TypeError, ValueError) as exc:
            raise PanelError(f"پاسخ نامعتبر S-UI هنگام {operation}: پاسخ JSON نبود.") from exc
        if not isinstance(payload, dict):
            raise PanelError(f"پاسخ نامعتبر S-UI هنگام {operation}.")
        if payload.get("success") is False:
            msg = str(payload.get("msg") or "عملیات ناموفق بود")
            if "token" in msg.lower() or "auth" in msg.lower() or "login" in msg.lower():
                raise PanelError("خطا در احراز هویت S-UI: API Token نامعتبر یا منقضی است.")
            raise PanelError(f"خطا در {operation}: {msg}")
        return payload.get("obj")

    @staticmethod
    def _items(obj, key: str) -> list:
        if isinstance(obj, list):
            return obj
        if isinstance(obj, dict):
            value = obj.get(key)
            return value if isinstance(value, list) else []
        return []

    @staticmethod
    def _config_dict(value) -> dict:
        """Normalize S-UI's JSON blob, which differs across panel builds."""
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except (TypeError, ValueError):
                return {}
            return parsed if isinstance(parsed, dict) else {}
        return {}

    def _inbound_ids(self) -> list[int]:
        keys = self.server.keys()
        raw = self.server["xui_inbound_ids"] if "xui_inbound_ids" in keys else None
        if raw:
            try:
                ids = json.loads(raw)
                if isinstance(ids, list) and ids:
                    return [int(value) for value in ids]
            except (TypeError, ValueError):
                pass
        legacy = self.server["xui_inbound_id"] if "xui_inbound_id" in keys else None
        return [int(legacy)] if legacy else []

    async def _list_clients(self, session: aiohttp.ClientSession) -> list:
        obj = await self._request_json(
            session, "GET", "clients", operation="دریافت فهرست کاربران",
        )
        return self._items(obj, "clients")

    async def _find_client(self, session: aiohttp.ClientSession, username: str,
                           *, required: bool = True) -> dict | None:
        summary = next((c for c in await self._list_clients(session) if c.get("name") == username), None)
        if summary is None:
            if required:
                raise PanelError(f"کاربری با نام «{username}» روی پنل S-UI پیدا نشد.")
            return None

        client_id = summary.get("id")
        if client_id is None:
            return summary
        obj = await self._request_json(
            session, "GET", "clients", params={"id": client_id},
            operation="دریافت اطلاعات کاربر",
        )
        full = self._items(obj, "clients")
        return full[0] if full else summary

    async def _save(self, session: aiohttp.ClientSession, action: str, data, *, operation: str):
        return await self._request_json(
            session,
            "POST",
            "save",
            operation=operation,
            form={"object": "clients", "action": action, "data": json.dumps(data, separators=(",", ":"))},
        )

    @staticmethod
    def _random_seq(length: int = 16) -> str:
        alphabet = string.ascii_letters + string.digits
        return "".join(secrets.choice(alphabet) for _ in range(length))

    @staticmethod
    def _ss_password(length: int) -> str:
        return base64.b64encode(secrets.token_bytes(length)).decode("ascii")

    @classmethod
    def _random_configs(cls, username: str) -> dict:
        password = cls._random_seq(16)
        shared_uuid = str(uuid.uuid4())
        return {
            "mixed": {"username": username, "password": password},
            "socks": {"username": username, "password": password},
            "http": {"username": username, "password": password},
            "shadowsocks": {"name": username, "password": cls._ss_password(32)},
            "shadowsocks16": {"name": username, "password": cls._ss_password(16)},
            "shadowtls": {"name": username, "password": cls._ss_password(32)},
            "vmess": {"name": username, "uuid": shared_uuid, "alterId": 0},
            "vless": {"name": username, "uuid": shared_uuid, "flow": "xtls-rprx-vision"},
            "anytls": {"name": username, "password": password},
            "trojan": {"name": username, "password": password},
            "naive": {"username": username, "password": password},
            "hysteria": {"name": username, "auth_str": password},
            "tuic": {"name": username, "uuid": str(uuid.uuid4()), "password": password},
            "hysteria2": {"name": username, "password": password},
        }

    @classmethod
    def _new_client(cls, username: str, inbound_ids: list[int], volume_gb: int,
                    duration_days: int) -> dict:
        now = int(time.time())
        return {
            "enable": True,
            "name": username,
            "subSecret": secrets.token_urlsafe(24),
            "config": cls._random_configs(username),
            "inbounds": inbound_ids,
            "links": [],
            "volume": int(volume_gb * (1024 ** 3)),
            "expiry": now + int(duration_days * 86400) if duration_days else 0,
            "up": 0,
            "down": 0,
            "desc": "",
            "group": "",
            "remark": username,
            "delayStart": False,
            "autoReset": False,
            "resetDays": 0,
            "nextReset": 0,
            "totalUp": 0,
            "totalDown": 0,
        }

    def _subscription_url(self, client: dict) -> str:
        base = (self.server["xui_sub_base_url"] or "").rstrip("/")
        key = (
            client.get("subSecret") or client.get("sub_secret") or
            client.get("subId") or client.get("sub_id") or client.get("name")
        )
        return f"{base}/{key}" if base and key else ""

    @staticmethod
    def _set_sub_secret(client: dict) -> None:
        value = secrets.token_urlsafe(24)
        # S-UI-X serializes this database column as subSecret, while a few
        # compatible builds expose the legacy snake_case JSON key.
        client["sub_secret" if "sub_secret" in client else "subSecret"] = value

    async def list_inbounds(self) -> list:
        async with self._session() as session:
            obj = await self._request_json(
                session, "GET", "inbounds", operation="دریافت فهرست inboundها",
            )
        all_inbounds = self._items(obj, "inbounds")
        # S-UI includes a ``users`` field on management-only inbounds in some
        # releases.  Restrict the picker to protocols that can actually carry
        # client links so an API/TUN inbound cannot poison sing-box config.
        candidates = [
            item for item in all_inbounds
            if str(item.get("type", "")).lower() in _USER_INBOUND_TYPES
        ]
        return [
            {
                "id": int(item["id"]),
                "remark": item.get("tag") or f"inbound-{item['id']}",
                "protocol": item.get("type") or "unknown",
                "port": (
                    item.get("listen_port") or item.get("listenPort") or
                    item.get("port") or "—"
                ),
            }
            for item in candidates if item.get("id") is not None
        ]

    async def create_user(self, username: str, volume_gb: int, duration_days: int) -> PanelUserResult:
        inbound_ids = self._inbound_ids()
        if not inbound_ids or not self.server["xui_sub_base_url"]:
            raise PanelError("این سرور هنوز کامل تنظیم نشده (inbound یا آدرس Subscription خالی است).")
        async with self._session() as session:
            # Clone one existing S-UI client when available.  This preserves
            # version-specific protocol fields and avoids generating a
            # sing-box config that the installed S-UI build cannot validate.
            summaries = await self._list_clients(session)
            template = None
            if summaries:
                template_name = summaries[0].get("name")
                if template_name:
                    template = await self._find_client(session, template_name, required=False)
            if template:
                client = copy.deepcopy(template)
                client.pop("id", None)
                client["name"] = username
                client["remark"] = ""
                client["config"] = self._rotate_configs(
                    self._config_dict(client.get("config")), username
                )
                client["inbounds"] = inbound_ids
                client["links"] = []
                client["volume"] = int(volume_gb * (1024 ** 3))
                client["expiry"] = int(time.time()) + int(duration_days * 86400) if duration_days else 0
                client["up"] = 0
                client["down"] = 0
                client["totalUp"] = 0
                client["totalDown"] = 0
                client["enable"] = True
                self._set_sub_secret(client)
            else:
                client = self._new_client(username, inbound_ids, volume_gb, duration_days)
            try:
                await self._save(session, "new", client, operation="ساخت کاربر")
            except PanelError as exc:
                message = str(exc).lower()
                if "duplicate" in message or "already" in message or "وجود" in message:
                    raise PanelUsernameTakenError(
                        f"نام کاربری «{username}» روی پنل S-UI تکراری است"
                    ) from exc
                raise
            saved = await self._find_client(session, username)
        return PanelUserResult(username=username, subscription_url=self._subscription_url(saved), raw=saved)

    async def delete_user(self, username: str) -> bool:
        async with self._session() as session:
            client = await self._find_client(session, username, required=False)
            if client is None:
                return False
            await self._save(session, "del", int(client["id"]), operation="حذف کاربر")
        return True

    async def get_user_usage(self, username: str) -> dict:
        async with self._session() as session:
            client = await self._find_client(session, username)
        used = int(client.get("up") or 0) + int(client.get("down") or 0)
        limit = int(client.get("volume") or 0)
        expiry = int(client.get("expiry") or 0)
        if not client.get("enable", False):
            status = "disabled"
        elif expiry and expiry <= int(time.time()):
            status = "expired"
        elif limit and used >= limit:
            status = "limited"
        else:
            status = "active"
        return {"used_bytes": used, "data_limit_bytes": limit, "status": status}

    async def get_user(self, username: str) -> PanelUserResult:
        async with self._session() as session:
            client = await self._find_client(session, username)
        return PanelUserResult(username=username, subscription_url=self._subscription_url(client), raw=client)

    async def update_user(self, username: str, add_volume_gb: float = 0, add_days: int = 0,
                          reset_usage: bool = False) -> PanelUserResult:
        async with self._session() as session:
            client = copy.deepcopy(await self._find_client(session, username))
            if add_volume_gb:
                client["volume"] = int(client.get("volume") or 0) + int(add_volume_gb * (1024 ** 3))
            if add_days:
                now = int(time.time())
                current_expiry = int(client.get("expiry") or 0)
                client["expiry"] = max(now, current_expiry) + int(add_days * 86400)
            if reset_usage:
                if "totalUp" in client:
                    client["totalUp"] = int(client.get("totalUp") or 0) + int(client.get("up") or 0)
                if "totalDown" in client:
                    client["totalDown"] = int(client.get("totalDown") or 0) + int(client.get("down") or 0)
                client["up"] = 0
                client["down"] = 0
            client["enable"] = True
            await self._save(session, "edit", client, operation="به‌روزرسانی کاربر")
            saved = await self._find_client(session, username)
        return PanelUserResult(username=username, subscription_url=self._subscription_url(saved), raw=saved)

    @classmethod
    def _rotate_configs(cls, configs: dict, username: str = "") -> dict:
        configs = copy.deepcopy(configs or {})
        for protocol, config in configs.items():
            if not isinstance(config, dict):
                continue
            # Keep protocol-specific identity aligned with the cloned S-UI
            # client row; otherwise a new row can still expose the template
            # user's username/name in generated links.
            if username:
                if protocol in {"mixed", "socks", "http", "naive"}:
                    config["username"] = username
                elif protocol not in {"vmess", "vless"}:
                    config["name"] = username
            if protocol in {"mixed", "socks", "http", "anytls", "trojan", "naive", "hysteria2"}:
                config["password"] = cls._random_seq(16)
            elif protocol in {"shadowsocks", "shadowtls"}:
                config["password"] = cls._ss_password(32)
            elif protocol == "shadowsocks16":
                config["password"] = cls._ss_password(16)
            elif protocol == "hysteria":
                config["auth_str"] = cls._random_seq(16)
            elif protocol == "tuic":
                config["uuid"] = str(uuid.uuid4())
                config["password"] = cls._random_seq(16)
            elif protocol in {"vmess", "vless"}:
                config["uuid"] = str(uuid.uuid4())
                if username:
                    config["name"] = username
        return configs

    async def revoke_credentials(self, username: str) -> PanelUserResult:
        async with self._session() as session:
            client = copy.deepcopy(await self._find_client(session, username))
            client["config"] = self._rotate_configs(
                self._config_dict(client.get("config")), username
            )
            self._set_sub_secret(client)
            await self._save(session, "edit", client, operation="قطع دسترسی و ساخت لینک جدید")
            saved = await self._find_client(session, username)
        return PanelUserResult(username=username, subscription_url=self._subscription_url(saved), raw=saved)

    async def set_enabled(self, username: str, enabled: bool) -> None:
        async with self._session() as session:
            client = copy.deepcopy(await self._find_client(session, username))
            client["enable"] = bool(enabled)
            await self._save(session, "edit", client, operation="تغییر وضعیت کاربر")

    async def rename_user(self, username: str, new_username: str) -> str:
        async with self._session() as session:
            client = copy.deepcopy(await self._find_client(session, username))
            client["name"] = new_username
            try:
                await self._save(session, "edit", client, operation="تغییر نام کاربر")
            except PanelError as exc:
                message = str(exc).lower()
                if "duplicate" in message or "already" in message or "وجود" in message:
                    raise PanelUsernameTakenError(
                        f"نام کاربری «{new_username}» روی پنل S-UI تکراری است"
                    ) from exc
                raise
            saved = await self._find_client(session, new_username)
        return self._subscription_url(saved)

    async def test_connection(self) -> bool:
        try:
            await self.list_inbounds()
            return True
        except (aiohttp.ClientError, PanelError):
            return False
