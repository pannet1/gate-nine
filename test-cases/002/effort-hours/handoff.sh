#!/usr/bin/env bash
# Record the "estimated / actual effort hours" case for Work Platform (run 002).
# Source brief: "Work Platform — Test Manual.md" -> Feature list: Task Management
#   Estimated / actual effort hours | Gate-9 verified 2026-10-15
#   "Enter on create, confirm it persists after reload"
#
# The URL is read from url.txt. It is never inferred from a pattern, from a
# sibling case, or from BASE_URL. If url.txt is absent the URL is unknown and
# this script refuses to guess.
set -euo pipefail

cd /home/pannet1/gate-nine

CASE_DIR="test-cases/002/effort-hours"

if [[ ! -f "$CASE_DIR/url.txt" ]]; then
  echo "Missing $CASE_DIR/url.txt" >&2
  echo "Ask the developer for the real Work Platform tenant URL, then:" >&2
  echo "  echo '<url>' > $CASE_DIR/url.txt" >&2
  exit 1
fi

uv run playwright codegen \
  --load-storage=test-cases/002/auth.json \
  -o "$CASE_DIR/effort-hours.py" \
  "$(cat "$CASE_DIR/url.txt")"