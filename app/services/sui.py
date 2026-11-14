"""S-UI API v2 adapter used by the existing panel service contract.

The bot was originally written against PasarGuard.  This module translates the
small user/subscription contract used by the bot into S-UI clients while
leaving the original PasarGuard client and all of its UI available.
"""

from __future__ import annotations

import json
import logging
import secrets
import time
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit

import httpx

from app.config import get_settings, normalize_http_base_url
from app.services.pasarguard import PasarGuardError, WireGuardResponse
from app.services.security_policy import UnsafePgUrlError, assert_safe_pg_base_url

logger = logging.getLogger(__name__)

SUI_HTTP_TIMEOUT = httpx.Timeout(30.0, connect=10.0, pool=10.0)
SUI_HTTP_LIMITS = httpx.Limits(
    max_connections=16,
    max_keepalive_connections=8,
    keepalive_expiry=4.0,
)
SUI_CONNECT_RETRIES = 2
SUI_SUPPORTED_PROTOCOLS = frozenset(
    {
        "anytls",
        "http",
        "hysteria",
        "hysteria2",
        "mixed",
        "naive",
        "shadowsocks",
        "snell",
        "socks",
        "trojan",
        "tuic",
        "vless",
        "vmess",
    }
)
SUI_DISABLED_STATUSES = frozenset(
    {"disabled", "expired", "limited", "depleted", "revoked", "blocked"}
)


def _as_int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def _as_timestamp(value: Any) -> int:
    """Accept S-UI unix seconds and the ISO values emitted by PG payload helpers."""
    if value in (None, "") or isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return max(0, int(value))
    text = str(value).strip()
    if not text:
        return 0
    try:
        return max(0, int(float(text)))
    except (TypeError, ValueError, OverflowError):
        pass
    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return 0
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return max(0, int(moment.timestamp()))


def _as_ids(value: Any) -> list[int]:
    if value is None:
        return []
    values = value if isinstance(value, (list, tuple, set)) else str(value).split(",")
    result: list[int] = []
    for item in values:
        number = _as_int(item)
        if number > 0 and number not in result:
            result.append(number)
    return result


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except (TypeError, ValueError):
            return []
        return decoded if isinstance(decoded, list) else []
    return []


def _status(raw: dict[str, Any]) -> str:
    if not bool(raw.get("enable", False)):
        return "disabled"
    expiry = _as_timestamp(raw.get("expiry"))
    if expiry and expiry < int(time.time()):
        return "expired"
    volume = _as_int(raw.get("volume"))
    used = _as_int(raw.get("up")) + _as_int(raw.get("down"))
    if volume > 0 and used >= volume:
        return "limited"
    return "active"


class SuiClient:
    """Expose the PasarGuard-like methods consumed by PGClockBot services."""

    backend_kind = "sui"

    def __init__(
        self,
        *,
        settings: Any | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._cache_partition = secrets.token_hex(16)
        self.base_url = normalize_http_base_url(self.settings.sui_base_url or "")
        if self.base_url:
            try:
                self.base_url = assert_safe_pg_base_url(self.base_url, resolve_dns=False)
            except UnsafePgUrlError:
                logger.error("Refusing unsafe S-UI base URL")
                self.base_url = ""
        self._api_base = f"{self.base_url}/apiv2" if self.base_url else ""
        self._api_token = (self.settings.sui_api_token or "").replace("\r", "").strip()
        self._client = http_client or httpx.AsyncClient(
            base_url=self._api_base,
            timeout=SUI_HTTP_TIMEOUT,
            follow_redirects=False,
            limits=SUI_HTTP_LIMITS,
            transport=httpx.AsyncHTTPTransport(retries=SUI_CONNECT_RETRIES),
        )

    @property
    def uses_api_key(self) -> bool:
        return True

    @property
    def is_auth_ready(self) -> bool:
        return bool(self.base_url and self._api_token)

    async def close(self) -> None:
        await self._client.aclose()

    def _http(self) -> httpx.AsyncClient:
        if getattr(self._client, "is_closed", False):
            self._client = httpx.AsyncClient(
                base_url=self._api_base,
                timeout=SUI_HTTP_TIMEOUT,
                follow_redirects=False,
                limits=SUI_HTTP_LIMITS,
                transport=httpx.AsyncHTTPTransport(retries=SUI_CONNECT_RETRIES),
            )
        return self._client

    async def ensure_token(self) -> str:
        if not self.base_url:
            raise PasarGuardError("SUI_BASE_URL در .env تنظیم نشده است")
        if not self._api_token:
            raise PasarGuardError("SUI_API_TOKEN در .env تنظیم نشده است")
        if any(char in self._api_token for char in {"\r", "\n"}):
            raise PasarGuardError("SUI_API_TOKEN نامعتبر است")
        return self._api_token

    async def request(
        self,
        method: str,
        path: str,
        *,
        auth: bool = True,
        **kwargs: Any,
    ) -> Any:
        kwargs.pop("cache_max_age", None)
        kwargs.pop("last_good_ok", None)
        kwargs.pop("use_cache", None)
        kwargs.pop("resolve_api_base", None)
        headers = dict(kwargs.pop("headers", {}) or {})
        if auth:
            headers["Token"] = await self.ensure_token()
        try:
            response = await self._http().request(
                method.upper(), path.lstrip("/"), headers=headers, **kwargs
            )
        except httpx.HTTPError as exc:
            raise PasarGuardError("ارتباط با S-UI ناموفق بود") from exc
        if response.status_code >= 400:
            detail = (response.text or "")[:300]
            raise PasarGuardError(
                f"S-UI {method.upper()} {path} failed ({response.status_code})",
                response.status_code,
                detail,
            )
        if response.status_code == 204 or not response.content:
            return None
        try:
            payload = response.json()
        except (TypeError, ValueError):
            return response.text
        if isinstance(payload, dict) and "success" in payload:
            if not bool(payload.get("success")):
                raise PasarGuardError(
                    str(payload.get("msg") or "S-UI request failed"),
                    400,
                    payload,
                )
            return payload.get("obj")
        return payload

    @staticmethod
    def _rows(data: Any, key: str) -> list[dict[str, Any]]:
        if isinstance(data, list):
            return [row for row in data if isinstance(row, dict)]
        if not isinstance(data, dict):
            return []
        rows = data.get(key)
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
        for fallback in ("items", "data", "results"):
            rows = data.get(fallback)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
        return []

    async def _raw_user_by_id(self, user_id: int) -> dict[str, Any]:
        data = await self.request("GET", "clients", params={"id": str(int(user_id))})
        rows = self._rows(data, "clients")
        if not rows:
            raise PasarGuardError("کاربر در S-UI پیدا نشد", 404)
        return rows[0]

    async def _raw_user_by_name(self, username: str) -> dict[str, Any]:
        wanted = (username or "").strip().lower()
        if not wanted:
            raise PasarGuardError("نام کاربر نامعتبر است", 400)
        data = await self.request("GET", "clients")
        for row in self._rows(data, "clients"):
            if str(row.get("name") or "").strip().lower() == wanted:
                return row
        raise PasarGuardError("کاربر در S-UI پیدا نشد", 404)

    def _subscription_url(self, name: str) -> str:
        configured = normalize_http_base_url(
            self.settings.sui_subscription_base_url or ""
        )
        if not configured:
            parsed = urlsplit(self.base_url)
            host = parsed.hostname or ""
            if ":" in host and not host.startswith("["):
                host = f"[{host}]"
            netloc = host
            if netloc:
                netloc += ":2096"
            configured = urlunsplit((parsed.scheme, netloc, "/sub", "", ""))
        return f"{configured.rstrip('/')}/{quote(name, safe='')}"

    def _to_pg_user(self, raw: dict[str, Any]) -> dict[str, Any]:
        name = str(raw.get("name") or "").strip()
        inbounds = _as_ids(_json_list(raw.get("inbounds")))
        volume = max(0, _as_int(raw.get("volume")))
        expiry = _as_timestamp(raw.get("expiry"))
        up = max(0, _as_int(raw.get("up")))
        down = max(0, _as_int(raw.get("down")))
        used = up + down
        subscription_url = self._subscription_url(name) if name else None
        return {
            "id": raw.get("id"),
            "username": name,
            "name": name,
            "status": _status(raw),
            "enable": bool(raw.get("enable", False)),
            "data_limit": volume,
            "volume": volume,
            "expire": expiry,
            "expiry": expiry,
            "up": up,
            "down": down,
            "used_traffic": used,
            "subscription_url": subscription_url,
            "subscription": subscription_url,
            "subscription_token": name,
            "group_ids": inbounds,
            "inbound_ids": inbounds,
            "inbounds": inbounds,
            "note": raw.get("desc") or raw.get("remark") or "",
            "desc": raw.get("desc") or "",
            "remark": raw.get("remark") or "",
            "links": _json_list(raw.get("links")),
            "raw": raw,
        }

    async def get_user_by_username(self, username: str) -> dict[str, Any]:
        return self._to_pg_user(await self._raw_user_by_name(username))

    async def get_user_by_id(self, user_id: int) -> dict[str, Any]:
        return self._to_pg_user(await self._raw_user_by_id(int(user_id)))

    async def get_users(
        self,
        *,
        cache_max_age: float | None = None,
        last_good_ok: bool = False,
        **params: Any,
    ) -> dict[str, Any]:
        del cache_max_age, last_good_ok
        data = await self.request("GET", "clients")
        users = [self._to_pg_user(row) for row in self._rows(data, "clients")]
        username = str(params.get("username") or params.get("search") or "").strip().lower()
        if username:
            users = [user for user in users if username in str(user.get("username") or "").lower()]
        total = len(users)
        offset = max(0, _as_int(params.get("offset")))
        limit = _as_int(params.get("limit"), 0)
        if limit > 0:
            users = users[offset : offset + limit]
        elif offset:
            users = users[offset:]
        return {"users": users, "total": total}

    async def get_inbounds(self) -> list[dict[str, Any]]:
        data = await self.request("GET", "inbounds")
        return self._rows(data, "inbounds")

    async def get_inbounds_details(self) -> list[dict[str, Any]]:
        return await self.get_inbounds()

    async def get_groups_simple(
        self,
        *,
        cache_max_age: float | None = None,
        last_good_ok: bool = False,
    ) -> list[dict[str, Any]]:
        del cache_max_age, last_good_ok
        groups: list[dict[str, Any]] = []
        for inbound in await self.get_inbounds():
            protocol = str(inbound.get("type") or "").lower()
            inbound_id = _as_int(inbound.get("id"))
            if inbound_id <= 0 or protocol not in SUI_SUPPORTED_PROTOCOLS:
                continue
            groups.append(
                {
                    "id": inbound_id,
                    "name": str(inbound.get("tag") or f"inbound-{inbound_id}"),
                    "tag": inbound.get("tag") or "",
                    "type": protocol,
                    "enable": bool(inbound.get("enable", True)),
                    "inbound_ids": [inbound_id],
                    "inbound_tags": [inbound.get("tag") or ""],
                }
            )
        return groups

    async def get_groups(self) -> dict[str, Any]:
        return {"groups": await self.get_groups_simple()}

    async def get_group(self, group_id: int) -> dict[str, Any]:
        for group in await self.get_groups_simple():
            if int(group.get("id") or 0) == int(group_id):
                return group
        raise PasarGuardError("Inbound در S-UI پیدا نشد", 404)

    async def _inbound_map(self) -> dict[int, dict[str, Any]]:
        result: dict[int, dict[str, Any]] = {}
        for inbound in await self.get_inbounds():
            inbound_id = _as_int(inbound.get("id"))
            if inbound_id > 0:
                result[inbound_id] = inbound
        return result

    async def _resolve_inbound_ids(self, requested: Any = None) -> list[int]:
        inbound_map = await self._inbound_map()
        ids = _as_ids(requested)
        if not ids:
            ids = _as_ids(self.settings.sui_inbound_ids)
        if not ids:
            ids = [
                inbound_id
                for inbound_id, inbound in inbound_map.items()
                if bool(inbound.get("enable", True))
                and str(inbound.get("type") or "").lower() in SUI_SUPPORTED_PROTOCOLS
            ]
        missing = [inbound_id for inbound_id in ids if inbound_id not in inbound_map]
        if missing:
            raise PasarGuardError(f"Inbound های S-UI پیدا نشدند: {missing}", 404)
        unsupported = [
            inbound_id
            for inbound_id in ids
            if str(inbound_map[inbound_id].get("type") or "").lower()
            not in SUI_SUPPORTED_PROTOCOLS
        ]
        if unsupported:
            raise PasarGuardError("Inbound انتخاب‌شده برای ساخت لینک قابل استفاده نیست", 400)
        if not ids:
            raise PasarGuardError(
                "هیچ Inbound قابل لینکی در S-UI پیدا نشد؛ SUI_INBOUND_IDS را تنظیم کنید",
                400,
            )
        return ids

    @staticmethod
    def _build_config(name: str, protocols: set[str]) -> dict[str, dict[str, str]]:
        client_uuid = str(uuid.uuid4())
        password = secrets.token_urlsafe(24)
        userkey = secrets.token_urlsafe(24)
        config: dict[str, dict[str, str]] = {}
        for protocol in protocols:
            if protocol in {"vless", "vmess"}:
                config[protocol] = {"name": name, "uuid": client_uuid}
            elif protocol in {"trojan", "hysteria2", "anytls"}:
                config[protocol] = {"name": name, "password": password}
            elif protocol == "shadowsocks":
                config[protocol] = {
                    "name": name,
                    "password": password,
                    "shadowsocks": password,
                    "shadowsocks16": password,
                }
            elif protocol == "snell":
                config[protocol] = {"name": name, "userkey": userkey}
            elif protocol in {"socks", "http", "mixed", "naive"}:
                config[protocol] = {"username": name, "password": password}
            elif protocol == "hysteria":
                config[protocol] = {"auth_str": password}
            elif protocol == "tuic":
                config[protocol] = {"name": name, "uuid": client_uuid, "password": password}
        if not config:
            raise PasarGuardError("پروتکل Inbound انتخاب‌شده در S-UI پشتیبانی نمی‌شود", 400)
        return config

    @staticmethod
    def _validate_name(value: Any) -> str:
        name = str(value or "").strip()
        if not name or any(char in name for char in "\r\n?#\\"):
            raise PasarGuardError("نام کاربر برای لینک اشتراک نامعتبر است", 400)
        return name

    async def _client_data_from_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        name = self._validate_name(payload.get("username") or payload.get("name"))
        inbound_ids = await self._resolve_inbound_ids(
            payload.get("group_ids") or payload.get("inbound_ids")
        )
        inbound_map = await self._inbound_map()
        protocols = {
            str(inbound_map[inbound_id].get("type") or "").lower()
            for inbound_id in inbound_ids
        }
        status = str(payload.get("status") or "active").lower().replace("-", "_")
        note = str(payload.get("note") or payload.get("remark") or "").strip()
        return {
            "enable": status not in SUI_DISABLED_STATUSES,
            "name": name,
            "config": self._build_config(name, protocols),
            "inbounds": inbound_ids,
            "links": [],
            "volume": max(0, _as_int(payload.get("data_limit"))),
            "expiry": _as_timestamp(payload.get("expire")),
            "desc": note,
            "group": "",
            "remark": note or name,
            "delayStart": False,
            "autoReset": False,
            "resetDays": 0,
            "nextReset": 0,
        }

    async def _save_client(self, action: str, data: dict[str, Any] | int) -> Any:
        encoded = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        return await self.request(
            "POST",
            "save",
            data={"object": "clients", "action": action, "data": encoded},
        )

    async def create_user(self, payload: dict[str, Any]) -> dict[str, Any]:
        client_data = await self._client_data_from_payload(payload)
        await self._save_client("new", client_data)
        return await self.get_user_by_username(str(client_data["name"]))

    async def create_user_from_template(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("user_template_id") or payload.get("template_id"):
            raise PasarGuardError(
                "Template های PasarGuard در حالت S-UI وجود ندارند؛ برای پلن، Inbound های S-UI را انتخاب کنید",
                501,
            )
        return await self.create_user(payload)

    async def modify_user_by_id(self, user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        raw = await self._raw_user_by_id(int(user_id))
        old_name = str(raw.get("name") or "")
        if payload.get("username") is not None:
            raw["name"] = self._validate_name(payload.get("username"))
        if "group_ids" in payload or "inbound_ids" in payload:
            raw["inbounds"] = await self._resolve_inbound_ids(
                payload.get("group_ids") or payload.get("inbound_ids")
            )
        if "data_limit" in payload:
            raw["volume"] = max(0, _as_int(payload.get("data_limit")))
        if "expire" in payload:
            raw["expiry"] = _as_timestamp(payload.get("expire"))
        if "status" in payload:
            status = str(payload.get("status") or "active").lower().replace("-", "_")
            raw["enable"] = status not in SUI_DISABLED_STATUSES
        if payload.get("note") is not None:
            raw["desc"] = str(payload.get("note") or "").strip()
            raw["remark"] = raw["desc"] or raw.get("remark") or old_name
        await self._save_client("edit", raw)
        if str(raw.get("name") or "") != old_name:
            return await self.get_user_by_username(str(raw["name"]))
        return await self.get_user_by_id(int(user_id))

    async def modify_user_with_template(self, user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("user_template_id") or payload.get("template_id"):
            raise PasarGuardError("Template در حالت S-UI پشتیبانی نمی‌شود", 501)
        return await self.modify_user_by_id(user_id, payload)

    async def delete_user_by_id(self, user_id: int) -> None:
        try:
            await self._save_client("del", int(user_id))
        except PasarGuardError as exc:
            if exc.status_code != 404:
                raise

    async def set_disabled_by_id(self, user_id: int, disabled: bool) -> dict[str, Any]:
        raw = await self._raw_user_by_id(int(user_id))
        raw["enable"] = not bool(disabled)
        await self._save_client("edit", raw)
        return await self.get_user_by_id(int(user_id))

    async def revoke_sub_by_id(self, user_id: int) -> dict[str, Any]:
        return await self.set_disabled_by_id(user_id, True)

    async def reset_user_by_id(self, user_id: int) -> dict[str, Any]:
        # S-UI's resetTraffic endpoint is global. Never call it for a single
        # customer; renewal still updates the quota and expiry safely.
        logger.warning("S-UI has no per-client traffic reset; user=%s was not reset", user_id)
        return await self.get_user_by_id(int(user_id))

    async def set_owner_by_id(self, user_id: int, admin_username: str) -> dict[str, Any]:
        del admin_username
        return await self.get_user_by_id(int(user_id))

    async def get_user_usage(self, user_id: int) -> dict[str, int]:
        user = await self.get_user_by_id(int(user_id))
        return {
            "up": _as_int(user.get("up")),
            "down": _as_int(user.get("down")),
            "used_traffic": _as_int(user.get("used_traffic")),
            "data_limit": _as_int(user.get("data_limit")),
        }

    async def subscription_info(
        self,
        token: str,
        *,
        subscription_url: str | None = None,
    ) -> dict[str, Any]:
        del subscription_url
        candidate = (token or "").strip().rstrip("/")
        if "://" in candidate:
            candidate = urlsplit(candidate).path.rstrip("/").rsplit("/", 1)[-1]
        elif "/" in candidate:
            candidate = candidate.rsplit("/", 1)[-1]
        if not candidate:
            raise PasarGuardError("توکن اشتراک نامعتبر است", 400)
        return await self.get_user_by_username(candidate)

    async def subscription_usage(
        self,
        token: str,
        *,
        subscription_url: str | None = None,
    ) -> dict[str, int]:
        user = await self.subscription_info(token, subscription_url=subscription_url)
        return {
            "upload": _as_int(user.get("up")),
            "download": _as_int(user.get("down")),
            "used_traffic": _as_int(user.get("used_traffic")),
            "data_limit": _as_int(user.get("data_limit")),
            "expire": _as_int(user.get("expire")),
        }

    async def subscription_xray(
        self,
        token: str,
        *,
        subscription_url: str | None = None,
    ) -> list[dict[str, Any]]:
        del token, subscription_url
        return []

    async def subscription_wireguard_bytes(
        self,
        token: str,
        *,
        subscription_url: str | None = None,
    ) -> WireGuardResponse:
        del token, subscription_url
        return WireGuardResponse(status=404, data=None)

    async def get_user_templates(self) -> dict[str, list[Any]]:
        return {"templates": []}

    async def get_user_templates_simple(self) -> list[dict[str, Any]]:
        return []

    def _unsupported(self, operation: str) -> None:
        raise PasarGuardError(
            f"عملیات «{operation}» در S-UI معادل ندارد؛ از مدیریت Inbound و Client خود S-UI استفاده کنید",
            501,
        )

    async def create_user_template(self, payload: dict[str, Any]) -> dict[str, Any]:
        del payload
        self._unsupported("Template")
        return {}

    async def get_user_template(self, template_id: int) -> dict[str, Any]:
        del template_id
        self._unsupported("Template")
        return {}

    async def delete_user_template(self, template_id: int) -> None:
        del template_id
        self._unsupported("Template")

    async def modify_user_template(self, template_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        del template_id, payload
        self._unsupported("Template")
        return {}

    async def create_group(self, payload: dict[str, Any]) -> dict[str, Any]:
        del payload
        self._unsupported("Group")
        return {}

    async def modify_group(self, group_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        del group_id, payload
        self._unsupported("Group")
        return {}

    async def delete_group(self, group_id: int) -> None:
        del group_id
        self._unsupported("Group")

    async def set_group_disabled(self, group_id: int, disabled: bool) -> Any:
        del group_id, disabled
        self._unsupported("Group")
        return None

    async def get_hosts(self, *, cache_max_age: float | None = None, last_good_ok: bool = False) -> list[dict[str, Any]]:
        del cache_max_age, last_good_ok
        return []

    async def get_host(self, host_id: int) -> dict[str, Any]:
        del host_id
        self._unsupported("Host")
        return {}

    async def create_host(self, payload: dict[str, Any]) -> dict[str, Any]:
        del payload
        self._unsupported("Host")
        return {}

    async def modify_host(self, host_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        del host_id, payload
        self._unsupported("Host")
        return {}

    async def delete_host(self, host_id: int) -> None:
        del host_id
        self._unsupported("Host")

    async def set_host_disabled(self, host_id: int, disabled: bool) -> Any:
        del host_id, disabled
        self._unsupported("Host")
        return None

    async def get_nodes(self, *, cache_max_age: float | None = None, last_good_ok: bool = False) -> list[dict[str, Any]]:
        del cache_max_age, last_good_ok
        return []

    async def get_nodes_simple(self, *, cache_max_age: float | None = None) -> list[dict[str, Any]]:
        del cache_max_age
        return []

    async def get_nodes_realtime(self) -> dict[str, Any]:
        return {}

    async def get_node(self, node_id: int) -> dict[str, Any]:
        del node_id
        self._unsupported("Node")
        return {}

    async def create_node(self, payload: dict[str, Any]) -> dict[str, Any]:
        del payload
        self._unsupported("Node")
        return {}

    async def modify_node(self, node_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        del node_id, payload
        self._unsupported("Node")
        return {}

    async def delete_node(self, node_id: int) -> Any:
        del node_id
        self._unsupported("Node")
        return None

    async def reset_node(self, node_id: int) -> Any:
        del node_id
        self._unsupported("Node")
        return None

    async def sync_node(self, node_id: int) -> Any:
        del node_id
        self._unsupported("Node")
        return None

    async def reconnect_node(self, node_id: int) -> Any:
        del node_id
        self._unsupported("Node")
        return None

    async def reconnect_all_nodes(self) -> Any:
        self._unsupported("Node")
        return None

    def _admin(self) -> dict[str, Any]:
        username = str(self.settings.sui_admin_username or "s-ui").strip() or "s-ui"
        return {
            "id": 0,
            "username": username,
            "status": "active",
            "is_active": True,
            "is_owner": True,
            "role": {"id": 1, "name": "owner"},
            "role_id": 1,
            "permissions": ["*"],
        }

    async def get_admins(self) -> list[dict[str, Any]]:
        return [self._admin()]

    async def get_admins_simple(
        self,
        *,
        cache_max_age: float | None = None,
        last_good_ok: bool = False,
    ) -> list[dict[str, Any]]:
        del cache_max_age, last_good_ok
        return await self.get_admins()

    async def get_current_admin(self, *, last_good_ok: bool = False) -> dict[str, Any]:
        del last_good_ok
        return self._admin()

    async def get_admin(self, username: str) -> dict[str, Any] | None:
        admin = self._admin()
        return admin if str(username or "").strip().lower() == admin["username"].lower() else None

    async def get_admin_gate(self, username: str) -> tuple[str, dict[str, Any] | None]:
        admin = await self.get_admin(username)
        return ("ok", admin) if admin else ("missing", None)

    async def get_admin_roles(self) -> list[dict[str, Any]]:
        return [{"id": 1, "name": "owner", "display_name": "S-UI owner"}]

    async def get_admin_role(self, role_id: int) -> dict[str, Any]:
        if int(role_id) != 1:
            raise PasarGuardError("Role در S-UI پیدا نشد", 404)
        return {"id": 1, "name": "owner", "permissions": ["*"]}

    async def create_admin(self, payload: dict[str, Any]) -> dict[str, Any]:
        del payload
        self._unsupported("Admin")
        return {}

    async def modify_admin(self, username: str, payload: dict[str, Any]) -> dict[str, Any]:
        del username, payload
        self._unsupported("Admin")
        return {}

    async def delete_admin(self, username: str) -> Any:
        del username
        self._unsupported("Admin")
        return None

    async def get_system_stats(
        self,
        *,
        cache_max_age: float | None = None,
        last_good_ok: bool = False,
    ) -> dict[str, Any]:
        del cache_max_age, last_good_ok
        data = await self.request(
            "GET",
            "status",
            params={"r": "cpu,mem,net,sys,sbd"},
        )
        return data if isinstance(data, dict) else {"raw": data}

