"""Validate the deliberately limited native PasarGuard Xray route format."""

from __future__ import annotations

import base64
import ipaddress
import re
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BeforeValidator, BaseModel, ConfigDict, Field, SecretStr, ValidationError, field_validator, model_validator

from app.services.connection_monitor_types import MonitorConfigError, MonitorIssue


class _StrictModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", hide_input_in_errors=True)


def static_hostname(value: str) -> str:
    """Accept literal IPs and DNS names, never templates, URLs or wildcards."""
    if not value or len(value) > 253 or value != value.strip():
        raise ValueError("invalid hostname")
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        pass
    labels = value.rstrip(".").split(".")
    if not all(re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label) for label in labels):
        raise ValueError("invalid hostname")
    return value.lower().rstrip(".")


class _User(_StrictModel):
    id: SecretStr
    encryption: Literal["none"]
    flow: Literal["", "xtls-rprx-vision"] = ""

    @field_validator("id")
    @classmethod
    def valid_uuid(cls, value: SecretStr) -> SecretStr:
        UUID(value.get_secret_value())
        return value


class _Server(_StrictModel):
    address: str
    port: Annotated[int, Field(ge=1, le=65535)]
    users: Annotated[list[_User], Field(min_length=1, max_length=1)]

    _address = field_validator("address")(static_hostname)


class _Settings(_StrictModel):
    vnext: Annotated[list[_Server], Field(min_length=1, max_length=1)]


_Fingerprint = Literal["", "chrome", "firefox", "safari", "ios", "android", "edge", "random", "randomized"]


def _false_only(value: object) -> object:
    if value is not False:
        raise ValueError("verification cannot be disabled")
    return value


_FalseOnly = Annotated[Literal[False], BeforeValidator(_false_only)]


class _TLS(_StrictModel):
    serverName: str
    allowInsecure: _FalseOnly = False
    show: _FalseOnly = False
    fingerprint: _Fingerprint = ""
    alpn: Annotated[list[Literal["h2", "http/1.1"]], Field(max_length=2)] = Field(default_factory=list)

    _server_name = field_validator("serverName")(static_hostname)


class _Reality(_StrictModel):
    serverName: str
    fingerprint: _Fingerprint
    publicKey: str
    shortId: str
    spiderX: Annotated[str, Field(max_length=2048)] = ""
    show: _FalseOnly = False

    _server_name = field_validator("serverName")(static_hostname)

    @field_validator("publicKey")
    @classmethod
    def valid_key(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_-]{43}", value):
            raise ValueError("invalid public key")
        if len(base64.urlsafe_b64decode(value + "=")) != 32:
            raise ValueError("invalid public key")
        return value

    @field_validator("shortId")
    @classmethod
    def valid_short_id(cls, value: str) -> str:
        if len(value) % 2 or not re.fullmatch(r"[0-9a-fA-F]{0,16}", value):
            raise ValueError("invalid short id")
        return value


class _WS(_StrictModel):
    path: Annotated[str, Field(max_length=2048)] = "/"
    host: str = ""
    headers: Annotated[dict[str, str], Field(max_length=16)] = Field(default_factory=dict)
    heartbeatPeriod: Annotated[int, Field(ge=0, le=3600)] | None = None

    @model_validator(mode="after")
    def static_settings(self) -> _WS:
        if not self.path.startswith("/") or any(ch in self.path for ch in "{}*\r\n"):
            raise ValueError("unsupported path")
        if self.host:
            static_hostname(self.host)
        for key, value in self.headers.items():
            if not re.fullmatch(r"[A-Za-z0-9-]{1,64}", key) or len(value) > 2048:
                raise ValueError("invalid header")
            if any(ch in value for ch in "{}*\r\n"):
                raise ValueError("unsupported header")
        return self


class _RawHeader(_StrictModel):
    type: Literal["none"]


class _Raw(_StrictModel):
    header: _RawHeader


class _Stream(_StrictModel):
    network: Literal["tcp", "raw", "ws"]
    security: Literal["tls", "reality"]
    tlsSettings: _TLS | None = None
    realitySettings: _Reality | None = None
    wsSettings: _WS | None = None
    tcpSettings: _Raw | None = None
    rawSettings: _Raw | None = None

    @model_validator(mode="after")
    def supported_combination(self) -> _Stream:
        if self.network == "ws":
            valid = self.security == "tls" and self.tlsSettings and self.wsSettings
            valid = valid and not (self.realitySettings or self.tcpSettings or self.rawSettings)
        else:
            valid = self.security == "reality" and self.realitySettings
            valid = valid and not (self.tlsSettings or self.wsSettings)
            valid = valid and not (self.tcpSettings and self.network != "tcp")
            valid = valid and not (self.rawSettings and self.network != "raw")
        if not valid:
            raise ValueError("unsupported transport")
        return self


class NativeMonitorOutbound(_StrictModel):
    protocol: Literal["vless"]
    tag: Literal["proxy"]
    settings: _Settings
    streamSettings: _Stream

    @model_validator(mode="after")
    def compatible_flow(self) -> NativeMonitorOutbound:
        if self.streamSettings.network == "ws" and self.settings.vnext[0].users[0].flow:
            raise ValueError("unsupported flow")
        return self

    def config(self) -> dict[str, Any]:
        result = self.model_dump(mode="json", exclude_none=True)
        result["settings"]["vnext"][0]["users"][0]["id"] = self.settings.vnext[0].users[0].id.get_secret_value()
        return result


def validate_native_outbound(payload: object) -> NativeMonitorOutbound:
    try:
        return NativeMonitorOutbound.model_validate(payload)
    except (ValidationError, ValueError):
        # Do not chain pydantic's payload-bearing errors into logs.
        raise MonitorConfigError(MonitorIssue.UNSUPPORTED) from None
