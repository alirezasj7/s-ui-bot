#!/usr/bin/env bash
# Lint ratchet: fail only when a changed Python file has MORE ruff findings than
# the same file on the base branch. Existing findings are tolerated; new ones
# are not, so quality can only go up. See ruff.toml and
# docs/ENGINEERING_REMEDIATION_PLAN.md.
#
# Usage:
#   scripts/lint_changed.sh              # compare against the merge-base with dev
#   scripts/lint_changed.sh upstream/dev # compare against an explicit ref
#   scripts/lint_changed.sh --details    # also print the findings of failing files
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

details=0
base_ref=""
for arg in "$@"; do
  case "$arg" in
    --details) details=1 ;;
    *) base_ref="$arg" ;;
  esac
done

if ! command -v ruff >/dev/null 2>&1; then
  echo "error: ruff is not installed (pip install ruff)" >&2
  exit 2
fi

if [ -z "$base_ref" ]; then
  for candidate in upstream/dev origin/dev dev; do
    if git rev-parse --verify --quiet "$candidate" >/dev/null; then
      base_ref="$candidate"
      break
    fi
  done
fi
if [ -z "$base_ref" ]; then
  echo "error: no base ref found; pass one explicitly (e.g. upstream/dev)" >&2
  exit 2
fi
base="$(git merge-base "$base_ref" HEAD)"

count_findings() {
  # Reads Python source on stdin; prints the number of findings.
  ruff check --quiet --stdin-filename "$1" --output-format concise - 2>/dev/null \
    | grep -c -E '^[^ ]+:[0-9]+:[0-9]+:' || true
}

failed=0
checked=0
while IFS= read -r file; do
  [ -f "$file" ] || continue
  checked=$((checked + 1))
  after="$(count_findings "$file" <"$file")"
  if git cat-file -e "$base:$file" 2>/dev/null; then
    before="$(git show "$base:$file" | count_findings "$file")"
  else
    before=0
  fi
  if [ "$after" -gt "$before" ]; then
    echo "FAIL $file: $before -> $after findings"
    if [ "$details" -eq 1 ]; then
      ruff check --quiet --output-format concise "$file" || true
    fi
    failed=1
  fi
done < <({ git diff --name-only --diff-filter=AM "$base" -- '*.py'; git ls-files --others --exclude-standard -- '*.py'; } | sort -u)

if [ "$failed" -ne 0 ]; then
  echo "Lint ratchet failed: new findings were introduced (base: $base_ref)." >&2
  exit 1
fi
echo "Lint ratchet passed: $checked changed Python file(s) did not gain findings (base: $base_ref)."
