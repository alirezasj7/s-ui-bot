"""Process runtime identity — changes on every real restart/re-exec."""

from __future__ import annotations

import os
import time
import uuid

BOOT_ID = uuid.uuid4().hex
BOOT_AT = time.time()
PID = os.getpid()
