#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

OUT_DIR="${1:-dist}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
ZIP_PATH="$OUT_DIR/bankguard-submission-$STAMP.zip"
STAGE="$(mktemp -d /tmp/opencode/bankguard-submit.XXXXXX)"
trap 'rm -rf "$STAGE"' EXIT

mkdir -p "$OUT_DIR" "$STAGE/BankGuard"

copy_path() {
  local src="$1"
  local dst="$STAGE/BankGuard/$src"
  mkdir -p "$(dirname "$dst")"
  if [ -d "$src" ]; then
    cp -a "$src" "$dst"
  else
    cp -a "$src" "$dst"
  fi
}

# Source and project files
for p in app data docs eval scripts tests ui AGENTS.md CONTRACT.md README.md requirements.txt pytest.ini .env.example .gitignore; do
  [ -e "$p" ] || continue
  copy_path "$p"
done

# Include heldout only if committed in git
if git ls-files --error-unmatch eval/cases/heldout.jsonl >/dev/null 2>&1; then
  mkdir -p "$STAGE/BankGuard/eval/cases"
  cp -a eval/cases/heldout.jsonl "$STAGE/BankGuard/eval/cases/heldout.jsonl"
fi

# Remove excluded artifacts anywhere in staged tree
find "$STAGE/BankGuard" -name '.env' -type f -delete
find "$STAGE/BankGuard" -name '*.db' -type f -delete
find "$STAGE/BankGuard" -name '__pycache__' -type d -prune -exec rm -rf {} +
find "$STAGE/BankGuard" -name '.venv' -type d -prune -exec rm -rf {} +
find "$STAGE/BankGuard" -name 'node_modules' -type d -prune -exec rm -rf {} +
rm -rf "$STAGE/BankGuard/eval/results/raw"

mkdir -p "$OUT_DIR"
rm -f "$ZIP_PATH"
(
  cd "$STAGE"
  zip -qry "$ROOT/$ZIP_PATH" BankGuard
)

echo "ZIP=$ZIP_PATH"
echo "== ZIP CONTENTS =="
unzip -l "$ZIP_PATH"
echo "== SENSITIVE CHECK =="
if unzip -l "$ZIP_PATH" | awk '{print $4}' | grep -E '(^|/)\.env$|\.db$' ; then
  echo "FOUND_SENSITIVE_FILES=1"
  exit 1
else
  echo "FOUND_SENSITIVE_FILES=0"
fi
EXTRACT="$(mktemp -d /tmp/opencode/bankguard-zipcheck.XXXXXX)"
trap 'rm -rf "$STAGE" "$EXTRACT"' EXIT
unzip -qq "$ZIP_PATH" -d "$EXTRACT"
# Exclude this script itself: it contains the literal pattern being checked.
if grep -RIn --binary-files=without-match --exclude-dir=.git --exclude='make_submission.sh' "sk-" "$EXTRACT" >/tmp/opencode/bankguard-sk-grep.txt; then
  echo "FOUND_SK_STRING=1"
  cat /tmp/opencode/bankguard-sk-grep.txt
  exit 1
else
  echo "FOUND_SK_STRING=0"
fi
