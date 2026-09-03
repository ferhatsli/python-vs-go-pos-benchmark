#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
POS_ROOT="${POS_ROOT:-}"
BENCH_ROOT="${BENCH_ROOT:-$ROOT}"
BASELINE_FILE="${ISOLATION_BASELINE_FILE:-$ROOT/.isolation/pos-status-baseline.txt}"
MODE="${ISOLATION_MODE:-strict}"
MANIFEST_FILE="${ISOLATION_MANIFEST_FILE:-$ROOT/docs/source-freeze/source-manifest.yaml}"
PUBLIC_PROVENANCE_FILE="${PUBLIC_PROVENANCE_FILE:-$ROOT/docs/source-freeze/public-provenance.json}"

if [[ "$MODE" == "public" ]]; then
  [[ -f "$PUBLIC_PROVENANCE_FILE" ]] || {
    echo "ERROR: public provenance is missing: $PUBLIC_PROVENANCE_FILE" >&2
    exit 13
  }
  if [[ ! -d "$BENCH_ROOT/.git" && ! -f "$BENCH_ROOT/.git" ]]; then
    echo "ERROR: BENCH_ROOT is not a git repository: $BENCH_ROOT" >&2
    exit 14
  fi

  status="$(git -C "$BENCH_ROOT" status --porcelain=v1 --untracked-files=all)"
  if [[ -n "$status" ]]; then
    if [[ "${BENCH_OVERWRITE:-0}" != "1" ]]; then
      echo "ERROR: benchmark worktree is not clean" >&2
      printf '%s\n' "$status" >&2
      exit 15
    fi
    while IFS= read -r line; do
      [[ -z "$line" ]] && continue
      path="${line:3}"
      path="${path%\"}"
      path="${path#\"}"
      case "$path" in
        results/*) ;;
        *)
          echo "ERROR: benchmark worktree is not clean outside generated results" >&2
          printf '%s\n' "$status" >&2
          exit 16
          ;;
      esac
    done <<< "$status"
  fi

  python3 - "$PUBLIC_PROVENANCE_FILE" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
if not payload.get("frozen_source_commit"):
    raise SystemExit("ERROR: public provenance missing frozen_source_commit")
if "protected_workloads" not in payload:
    raise SystemExit("ERROR: public provenance missing protected_workloads")
PY
  echo "PASS: public reproduction boundary verified"
  exit 0
fi

if [[ -z "$POS_ROOT" ]]; then
  echo "ERROR: POS_ROOT must be set for ISOLATION_MODE=$MODE" >&2
  exit 17
fi

case "$BENCH_ROOT" in
  "$POS_ROOT"|"$POS_ROOT"/*)
    echo "ERROR: benchmark workspace is nested in POS repository" >&2
    exit 2
    ;;
esac

if [[ ! -d "$POS_ROOT/.git" && ! -f "$POS_ROOT/.git" ]]; then
  echo "ERROR: POS_ROOT is not a git repository: $POS_ROOT" >&2
  exit 3
fi

case "$MODE" in
  strict)
    if [[ ! -f "$BASELINE_FILE" ]]; then
      echo "ERROR: isolation baseline is missing: $BASELINE_FILE" >&2
      exit 4
    fi
    current_status="$(mktemp)"
    trap 'rm -f "$current_status"' EXIT
    git -C "$POS_ROOT" status --porcelain=v1 > "$current_status"
    if ! diff -u "$BASELINE_FILE" "$current_status" >/dev/null; then
      echo "ERROR: POS repository status changed since benchmark baseline" >&2
      diff -u "$BASELINE_FILE" "$current_status" >&2 || true
      exit 5
    fi
    echo "PASS: benchmark workspace is isolated and POS repository status is unchanged"
    ;;
  workload)
    [[ -f "$MANIFEST_FILE" ]] || {
      echo "ERROR: source manifest is missing: $MANIFEST_FILE" >&2
      exit 6
    }
    python3 - "$POS_ROOT" "$MANIFEST_FILE" <<'PY'
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

root = Path(sys.argv[1])
manifest = Path(sys.argv[2])
lines = manifest.read_text(encoding="utf-8").splitlines()
files: dict[str, str] = {}
protected: set[str] = set()
section = ""
for line in lines:
    if line == "files:":
        section = "files"
        continue
    if line == "workloads:":
        section = "workloads"
        continue
    if section == "files":
        match = re.match(r"^  ([^:]+): ([0-9a-f]{64})$", line)
        if match:
            files[match.group(1)] = match.group(2)
    elif section == "workloads":
        match = re.match(r"^  - (.+)$", line)
        if match:
            protected.add(match.group(1))

if not protected:
    print("ERROR: no workload source paths found in manifest", file=sys.stderr)
    raise SystemExit(7)

failures: list[str] = []
for rel in sorted(protected):
    expected = files.get(rel)
    path = root / rel
    if expected is None:
        failures.append(f"{rel}: missing frozen hash")
        continue
    if not path.is_file():
        failures.append(f"{rel}: missing file")
        continue
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected:
        failures.append(f"{rel}: expected {expected}, got {actual}")

if failures:
    print("ERROR: protected workload source changed", file=sys.stderr)
    for failure in failures:
        print(f"- {failure}", file=sys.stderr)
    raise SystemExit(8)

print(f"PASS: workload source hashes unchanged ({len(protected)}/{len(protected)})")
PY
    ;;
  frozen)
    [[ -f "$MANIFEST_FILE" ]] || {
      echo "ERROR: source manifest is missing: $MANIFEST_FILE" >&2
      exit 6
    }
    python3 - "$POS_ROOT" "$MANIFEST_FILE" <<'PY'
from __future__ import annotations

import hashlib
import re
import subprocess
import sys
from pathlib import Path

root = Path(sys.argv[1])
manifest = Path(sys.argv[2])
lines = manifest.read_text(encoding="utf-8").splitlines()
files: dict[str, str] = {}
protected: set[str] = set()
head: str | None = None
section = ""
for line in lines:
    if line == "git:":
        section = "git"
        continue
    if line == "files:":
        section = "files"
        continue
    if line == "workloads:":
        section = "workloads"
        continue
    if section == "git":
        match = re.match(r"^  head: ([0-9a-f]{7,40})$", line)
        if match:
            head = match.group(1)
    elif section == "files":
        match = re.match(r"^  ([^:]+): ([0-9a-f]{64})$", line)
        if match:
            files[match.group(1)] = match.group(2)
    elif section == "workloads":
        match = re.match(r"^  - (.+)$", line)
        if match:
            protected.add(match.group(1))

if not head:
    print("ERROR: frozen git head missing from manifest", file=sys.stderr)
    raise SystemExit(10)
if not protected:
    print("ERROR: no workload source paths found in manifest", file=sys.stderr)
    raise SystemExit(7)

try:
    subprocess.run(["git", "-C", str(root), "cat-file", "-e", f"{head}^{{commit}}"], check=True, capture_output=True)
except subprocess.CalledProcessError:
    print(f"ERROR: frozen commit unavailable: {head}", file=sys.stderr)
    raise SystemExit(11)

failures: list[str] = []
for rel in sorted(protected):
    expected = files.get(rel)
    if expected is None:
        failures.append(f"{rel}: missing frozen hash")
        continue
    result = subprocess.run(["git", "-C", str(root), "show", f"{head}:{rel}"], capture_output=True)
    if result.returncode != 0:
        failures.append(f"{rel}: missing at frozen commit {head}")
        continue
    actual = hashlib.sha256(result.stdout).hexdigest()
    if actual != expected:
        failures.append(f"{rel}: expected {expected}, got {actual}")

if failures:
    print("ERROR: frozen workload source mismatch", file=sys.stderr)
    for failure in failures:
        print(f"- {failure}", file=sys.stderr)
    raise SystemExit(12)

print(f"PASS: frozen workload source hashes unchanged ({len(protected)}/{len(protected)}) at {head}")
PY
    ;;
  *)
    echo "ERROR: unsupported ISOLATION_MODE=$MODE (expected strict, workload, frozen or public)" >&2
    exit 9
    ;;
esac
