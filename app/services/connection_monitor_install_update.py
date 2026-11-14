"""Run the current installer after a web update without making optional-core failure fatal."""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path
from typing import Protocol


class UpdateRunner(Protocol):
    def __call__(self, command: list[str], *, cwd: Path, timeout: int) -> tuple[int, str]: ...


def setup_updated_monitor_core(root: Path, *, runner: UpdateRunner, log: Callable[[str], None]) -> None:
    log("نصب و تنظیم Xray برای تست اتصال…")
    code, _ = runner([sys.executable, "-m", "app.cli.connection_monitor_install", "--root", str(root)], cwd=root, timeout=120)
    log("Xray آماده است؛ تست اتصال را از تنظیمات روشن کنید." if code == 0 else
        "نصب Xray کامل نشد؛ آپدیت ربات ادامه دارد. برای تلاش دوباره، گزینهٔ Setup Xray را در اسکریپت انتخاب کنید.")
