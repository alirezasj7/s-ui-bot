"""Phase 6 architecture: reply keyboards extracted from keyboards god-file."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_reply_keyboards_module_exists_and_is_substantial():
    path = ROOT / "app" / "bot" / "reply_keyboards.py"
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "Extracted from" in text or "re-exported" in text
    # Core builders must live here (not only as empty stubs).
    for name in (
        "def main_reply_keyboard",
        "def admin_reply_keyboard",
        "def reply_action_map",
        "def admin_ops_reply_keyboard",
    ):
        assert name in text, name


def test_keyboards_reexports_reply_builders():
    kb_src = (ROOT / "app" / "bot" / "keyboards.py").read_text(encoding="utf-8")
    assert "from app.bot.reply_keyboards import" in kb_src
    # God-file should be smaller than the pre-extract ~3100 LOC baseline.
    assert kb_src.count("\n") < 2800

    from app.bot import keyboards as kb
    from app.bot import reply_keyboards as rk

    assert kb.main_reply_keyboard is rk.main_reply_keyboard
    assert kb.reply_action_map is rk.reply_action_map
    assert kb.admin_ops_reply_keyboard is rk.admin_ops_reply_keyboard
    assert kb.cancel_reply is rk.cancel_reply


def test_reply_action_map_still_security_scoped():
    """Admin/PG labels must not register on reseller bots (contract unchanged)."""
    from app.bot.keyboards import reply_action_map

    ui = {
        "menu_layout": "compact",
        "menu_order": "shop,wallet",
        "btn_shop": "خرید",
        "btn_wallet": "کیف",
        "btn_menu_home": "🏠 منوی اصلی",
        "btn_back": "⬅️ بازگشت",
        "btn_admin": "پنل ادمین",
        "btn_pg": "پاسارگارد",
    }
    mapping = reply_action_map(
        "user",
        ui=ui,
        include_submenus=True,
        is_reseller_bot=True,
    )
    assert "adm_dash" not in mapping.values()
    assert "pg_users" not in mapping.values()
