"""Panel provider registry.

This build intentionally supports only the stable S-UI-X panel.  Keeping the
registry small is deliberate: unsupported panel payloads must never reach the
sing-box core through this bot.
"""
import json

from .base import BasePanelProvider, PanelError, PanelUsernameTakenError, PanelUserResult
from .sui_provider import SUIProvider

PROVIDERS = {"sui": SUIProvider}
PANEL_TYPE_LABELS = {"sui": "S-UI-X"}

# S-UI-X needs a public subscription base URL and an explicit list of usable
# user inbounds.  It does not use the legacy template-based panel workflow.
TEMPLATE_BASED_PANEL_TYPES = set()
SUB_BASE_URL_PANEL_TYPES = {"sui"}
INBOUND_SELECT_PANEL_TYPES = {"sui"}


def parse_xui_inbound_ids(server) -> list:
    """Return the selected S-UI-X inbound ids.

    The database column names predate S-UI support, so both the JSON list and
    the old single-id column are accepted for backwards compatibility.
    """
    keys = server.keys()
    raw = server["xui_inbound_ids"] if "xui_inbound_ids" in keys else None
    if raw:
        try:
            ids = json.loads(raw)
            if isinstance(ids, list) and ids:
                return [int(value) for value in ids]
        except (ValueError, TypeError):
            pass
    legacy = server["xui_inbound_id"] if "xui_inbound_id" in keys else None
    return [int(legacy)] if legacy else []


def get_provider(server) -> BasePanelProvider:
    panel_type = server["panel_type"]
    cls = PROVIDERS.get(panel_type)
    if cls is None:
        raise PanelError(f"نوع پنل «{panel_type}» پشتیبانی نمی‌شود؛ فقط S-UI-X مجاز است.")
    return cls(server)


__all__ = [
    "BasePanelProvider", "PanelError", "PanelUsernameTakenError", "PanelUserResult",
    "SUIProvider", "PROVIDERS", "PANEL_TYPE_LABELS", "TEMPLATE_BASED_PANEL_TYPES",
    "SUB_BASE_URL_PANEL_TYPES", "INBOUND_SELECT_PANEL_TYPES", "parse_xui_inbound_ids",
    "get_provider",
]
