"""Cross-engine data validation for SQLite ↔ PostgreSQL migrations."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

from app.db import Base
import app.db.models  # noqa: F401
from app.db.engine_url import to_sync_url

log = logging.getLogger(__name__)

# Canonical table order for migration / validation (FK-safe).
TABLE_ORDER: tuple[str, ...] = (
    "bot_users",
    "reseller_plans",
    "plans",
    "user_services",
    "orders",
    "payments",
    "tickets",
    "ticket_messages",
    "pg_staff_access",
    "panel_tickets",
    "panel_ticket_messages",
    "discount_codes",
    "charge_codes",
    "charge_code_uses",
    "broadcast_logs",
    "reseller_profiles",
    "reseller_billing_transactions",
    "reseller_billing_rates",
    "reseller_settings",
    "reseller_applications",
    "settings",
    "wallet_transactions",
    "trial_claims",
    "charge_code_redemptions",
    "payment_receipt_fingerprints",
)

CRITICAL_TABLES = (
    "bot_users",
    "reseller_profiles",
    "pg_staff_access",
    "orders",
    "payments",
    "settings",
    "wallet_transactions",
    "reseller_billing_transactions",
    "tickets",
    "panel_tickets",
    "user_services",
    "plans",
)


@dataclass
class ValidationReport:
    ok: bool = True
    source_dialect: str = ""
    target_dialect: str = ""
    counts: dict[str, dict[str, int]] = field(default_factory=dict)
    mismatches: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    length_violations: list[dict[str, Any]] = field(default_factory=list)
    extras: dict[str, Any] = field(default_factory=dict)

    def fail(self, msg: str) -> None:
        self.ok = False
        self.mismatches.append(msg)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "source_dialect": self.source_dialect,
            "target_dialect": self.target_dialect,
            "counts": self.counts,
            "mismatches": self.mismatches,
            "warnings": self.warnings,
            "length_violations": self.length_violations,
            "extras": self.extras,
        }


def _engine(url: str) -> Engine:
    return create_engine(to_sync_url(url))


def table_counts(engine: Engine) -> dict[str, int]:
    insp = inspect(engine)
    out: dict[str, int] = {}
    with engine.connect() as conn:
        for name in TABLE_ORDER:
            if not insp.has_table(name):
                out[name] = -1
                continue
            out[name] = int(conn.execute(text(f"SELECT COUNT(*) FROM {name}")).scalar() or 0)
    return out


def scan_varchar_overflows(engine: Engine) -> list[dict[str, Any]]:
    """Find string values that exceed declared VARCHAR lengths (SQLite does not enforce)."""
    violations: list[dict[str, Any]] = []
    insp = inspect(engine)
    with engine.connect() as conn:
        for table in Base.metadata.sorted_tables:
            if not insp.has_table(table.name):
                continue
            for col in table.columns:
                if not hasattr(col.type, "length") or not col.type.length:
                    continue
                length = int(col.type.length)
                # dialect-agnostic length check via Python after fetch is safer for SQLite
                rows = conn.execute(
                    text(f"SELECT id, {col.name} AS v FROM {table.name} WHERE {col.name} IS NOT NULL")
                ).fetchall()
                for row in rows:
                    val = row.v
                    if isinstance(val, str) and len(val) > length:
                        violations.append(
                            {
                                "table": table.name,
                                "column": col.name,
                                "id": row.id,
                                "length": len(val),
                                "max": length,
                            }
                        )
    return violations


def compare_databases(source_url: str, target_url: str) -> ValidationReport:
    report = ValidationReport()
    src = _engine(source_url)
    dst = _engine(target_url)
    try:
        report.source_dialect = src.dialect.name
        report.target_dialect = dst.dialect.name
        src_counts = table_counts(src)
        dst_counts = table_counts(dst)
        for name in TABLE_ORDER:
            sc = src_counts.get(name, -1)
            dc = dst_counts.get(name, -1)
            report.counts[name] = {"source": sc, "target": dc}
            if sc < 0 and dc < 0:
                continue
            if sc != dc:
                msg = f"count mismatch {name}: source={sc} target={dc}"
                if name in CRITICAL_TABLES:
                    report.fail(msg)
                else:
                    report.warnings.append(msg)

        # Spot-check settings keys
        if src_counts.get("settings", 0) >= 0 and dst_counts.get("settings", 0) >= 0:
            with src.connect() as sc, dst.connect() as dc:
                sk = {r[0] for r in sc.execute(text("SELECT key FROM settings")).fetchall()}
                dk = {r[0] for r in dc.execute(text("SELECT key FROM settings")).fetchall()}
                if sk != dk:
                    report.fail(f"settings keys differ: only_src={sorted(sk - dk)} only_dst={sorted(dk - sk)}")
                report.extras["settings_keys"] = sorted(sk)

        # Wallet balance sanity: sum of users present
        if src_counts.get("bot_users", 0) > 0:
            with src.connect() as sc, dst.connect() as dc:
                sw = int(sc.execute(text("SELECT COALESCE(SUM(wallet_balance),0) FROM bot_users")).scalar() or 0)
                dw = int(dc.execute(text("SELECT COALESCE(SUM(wallet_balance),0) FROM bot_users")).scalar() or 0)
                report.extras["wallet_balance_sum"] = {"source": sw, "target": dw}
                if sw != dw:
                    report.fail(f"wallet_balance sum mismatch: source={sw} target={dw}")

        if src_counts.get("reseller_profiles", 0) > 0:
            with src.connect() as sc, dst.connect() as dc:
                sb = int(
                    sc.execute(text("SELECT COALESCE(SUM(billing_balance),0) FROM reseller_profiles")).scalar()
                    or 0
                )
                db = int(
                    dc.execute(text("SELECT COALESCE(SUM(billing_balance),0) FROM reseller_profiles")).scalar()
                    or 0
                )
                report.extras["billing_balance_sum"] = {"source": sb, "target": db}
                if sb != db:
                    report.fail(f"billing_balance sum mismatch: source={sb} target={db}")

        # Length violations on source (pre-migration gate)
        report.length_violations = scan_varchar_overflows(src)
        if report.length_violations:
            report.warnings.append(
                f"{len(report.length_violations)} VARCHAR length violation(s) on source "
                "(PostgreSQL will reject these unless truncated)"
            )
    finally:
        src.dispose()
        dst.dispose()
    return report


def validate_single(url: str) -> ValidationReport:
    """Validate a single database for schema presence and length overflows."""
    report = ValidationReport()
    eng = _engine(url)
    try:
        report.source_dialect = eng.dialect.name
        report.target_dialect = eng.dialect.name
        counts = table_counts(eng)
        for name, c in counts.items():
            report.counts[name] = {"source": c, "target": c}
            if c < 0 and name in CRITICAL_TABLES:
                report.fail(f"missing critical table: {name}")
        report.length_violations = scan_varchar_overflows(eng)
        if report.length_violations:
            report.warnings.append(f"{len(report.length_violations)} VARCHAR overflow(s)")
        # Referral index presence
        insp = inspect(eng)
        idx_names = set()
        if insp.has_table("wallet_transactions"):
            for ix in insp.get_indexes("wallet_transactions"):
                idx_names.add(ix.get("name") or "")
        report.extras["wallet_indexes"] = sorted(idx_names)
        if "uq_wallet_referral_reason" not in idx_names:
            report.warnings.append("missing uq_wallet_referral_reason index")
    finally:
        eng.dispose()
    return report
