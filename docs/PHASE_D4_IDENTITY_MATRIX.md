# Phase D4 — Identity Matrix (operators)

**Status:** Implemented with Phase D4  
**Audience:** Operators / Owner  
**Binding:** Web and Telegram Bot use the **same role boundaries**; shop ACL is shared; PG management on Bot is platform-admin only.

---

## Principals

| Principal | Web login | Shop (Web + Bot) | PasarGuard client | Telegram Bot |
|-----------|-----------|------------------|-------------------|--------------|
| Owner / platform Admin | `web_admin.json` → `role=admin` | Full | Owner `get_pg()` (env) | `ADMIN_IDS` and/or `BotUser.role=admin` |
| pg_staff | `PgStaffAccess` | **None** | `get_pg_for_staff` (enc required) | **None** (web-only) |
| Reseller | `ResellerProfile` | `web_permissions` (C4) | `get_pg_for_reseller` when linked | Shop menus on **shop bot**; credentials UX on main bot |
| Shop `bot_admin_ids` | No separate web login | Owner’s shop keys on shop bot | N/A | Telegram assistants only |

---

## Important separations (not bugs)

1. **Web Owner ≠ Bot admin automatically**  
   Putting someone in `ADMIN_IDS` does not create a web login, and vice versa. Configure both if the same person needs both channels.

2. **pg_staff has no Telegram identity**  
   Secondary PG admins use the web panel only. Do not expect shop or Bot PG tools.

3. **Reseller PG management is Web**  
   Bot shop tools cover orders/plans/tickets/etc. PasarGuard user/admin management for resellers is on the web PG pages (own client — never Owner token).

4. **`bot_permissions` column**  
   Written as a mirror of `web_permissions`. Authorization **reads** `web_permissions` only.

5. **Synthetic Telegram IDs**  
   Some provisioned resellers get negative internal `telegram_id`s. Notifications skip them; they are not real Telegram users.

---

## Where to change credentials

| Role | Path |
|------|------|
| Owner web | `/security` (does not change env `PG_PASSWORD` by default) |
| pg_staff | `/security` when username aligned; else Owner remediates on `/pg/admins` |
| Reseller | `/security` or Owner reseller edit |

In-product summary also appears on `/security` (Phase D4 help card).
