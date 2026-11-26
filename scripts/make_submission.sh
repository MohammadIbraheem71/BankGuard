#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

OUT_DIR="$(realpath -m "${1:-dist}")"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
ZIP_PATH="$OUT_DIR/bankguard-submission-$STAMP.zip"
STAGE="$(mktemp -d /tmp/opencode/bankguard-submit.XXXXXX)"
trap 'rm -rf "$STAGE"' EXIT

mkdir -p "$OUT_DIR" "$STAGE/BankGuard"

for required in docs/contributions eval/cases/heldout.jsonl eval/results/final_raw; do
  if [ ! -e "$required" ]; then
    echo "missing required submission path: $required" >&2
    exit 1
  fi
done

copy_path() {
  local src="$1"
  local dst="$STAGE/BankGuard/$src"
  mkdir -p "$(dirname "$dst")"
  cp -a "$src" "$dst"
}

# Source, docs, eval cases/results, tests, UI and project metadata.
for p in app data docs eval scripts tests ui AGENTS.md CONTRACT.md README.md \
         requirements.txt pytest.ini .env.example .gitignore; do
  [ -e "$p" ] || continue
  copy_path "$p"
done

# Remove excluded artifacts anywhere in the staged tree.
find "$STAGE/BankGuard" -name '.env' -type f -delete
find "$STAGE/BankGuard" -name '*.db' -type f -delete
find "$STAGE/BankGuard" -name '__pycache__' -type d -prune -exec rm -rf {} +
find "$STAGE/BankGuard" -name '.venv' -type d -prune -exec rm -rf {} +
find "$STAGE/BankGuard" -name '.pytest_cache' -type d -prune -exec rm -rf {} +
find "$STAGE/BankGuard" -name 'node_modules' -type d -prune -exec rm -rf {} +
rm -rf "$STAGE/BankGuard/eval/results/raw"
rm -rf "$STAGE/BankGuard/dist"

mkdir -p "$OUT_DIR"
rm -f "$ZIP_PATH"
(
  cd "$STAGE"
  zip -qry "$ZIP_PATH" BankGuard
)

echo "ZIP=$ZIP_PATH"
echo "== ZIP CONTENTS =="
unzip -l "$ZIP_PATH"
echo "== SENSITIVE CHECK =="
if unzip -l "$ZIP_PATH" | awk '{print $4}' | grep -E '(^|/)\.env$|\.db$'; then
  echo "FOUND_SENSITIVE_FILES=1"
  exit 1
else
  echo "FOUND_SENSITIVE_FILES=0"
fi
EXTRACT="$(mktemp -d /tmp/opencode/bankguard-zipcheck.XXXXXX)"
trap 'rm -rf "$STAGE" "$EXTRACT"' EXIT
unzip -qq "$ZIP_PATH" -d "$EXTRACT"
# Print filenames only, never matching line contents (held-out text may appear).
if grep -RIl --binary-files=without-match --exclude-dir=.git \
      --exclude='make_submission.sh' "sk-" "$EXTRACT" \
      >/tmp/opencode/bankguard-sk-files.txt; then
  echo "FOUND_SK_STRING=1"
  cat /tmp/opencode/bankguard-sk-files.txt
  exit 1
else
  echo "FOUND_SK_STRING=0"
fi
