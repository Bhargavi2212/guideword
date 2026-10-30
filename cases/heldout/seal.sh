#!/bin/sh
# Recompute SEALS.txt from cases/ and keys/ (sorted, LF).
cd "$(dirname "$0")" || exit 1
find cases keys -type f | LC_ALL=C sort | while read -r f; do
  printf '%s  %s  %s\n' "$(sha256sum "$f" | cut -d' ' -f1)" "$f" "$(date -u +%Y-%m-%d)"
done > SEALS.txt
