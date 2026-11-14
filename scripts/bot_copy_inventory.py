#!/usr/bin/env python3
"""Inventory of the Persian user-facing strings written in the bot's source.

Used when built-in texts are moved or reworded: take an inventory before the
change, another after it, and compare. A pure move (strings relocated into a
copy module, duplicates merged) shows no added or removed text, only lower
counts; anything else is listed for review.

Usage:
  python -m scripts.bot_copy_inventory > before.json
  python -m scripts.bot_copy_inventory --compare before.json
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCANNED_DIRS = ("app/bot", "app/services", "app/jobs")
_PERSIAN_RE = re.compile(r"[؀-ۿ]")


def _docstring_nodes(tree: ast.AST) -> set[int]:
    owners = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, owners) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                ids.add(id(first.value))
    return ids


def strings_in_file(path: Path) -> list[str]:
    """Persian string literals in *path*, including the literal parts of f-strings."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    docstrings = _docstring_nodes(tree)
    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        if id(node) in docstrings or not _PERSIAN_RE.search(node.value):
            continue
        found.append(node.value)
    return found


def build_inventory(root: Path = ROOT) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for directory in SCANNED_DIRS:
        for path in sorted((root / directory).rglob("*.py")):
            counts.update(strings_in_file(path))
    return dict(sorted(counts.items()))


def compare(before: dict[str, int], after: dict[str, int]) -> dict[str, object]:
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    recounted = {
        text: {"before": before[text], "after": after[text]}
        for text in sorted(set(before) & set(after))
        if before[text] != after[text]
    }
    return {"added": added, "removed": removed, "count_changed": recounted}


def main() -> int:
    parser = argparse.ArgumentParser(description="Inventory of built-in Persian bot texts")
    parser.add_argument("--compare", type=Path, help="earlier inventory JSON to diff against")
    args = parser.parse_args()

    inventory = build_inventory()
    if args.compare is None:
        print(json.dumps(inventory, ensure_ascii=False, indent=2))
        return 0
    before = json.loads(args.compare.read_text(encoding="utf-8"))
    report = compare(before, inventory)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report["added"] or report["removed"] else 0


if __name__ == "__main__":
    sys.exit(main())
