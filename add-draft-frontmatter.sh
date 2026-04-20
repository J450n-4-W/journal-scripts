#!/bin/bash
# add-draft-frontmatter.sh
# Batch-adds minimal frontmatter to markdown drafts and moves them into the vault.
# Skips files that already have frontmatter (start with '---').
# Extracts date from filename if present (YYYY-MM-DD or YYYY_MM_DD patterns).
# Falls back to filesystem mtime if no date in filename.
#
# Usage: ./add-draft-frontmatter.sh /path/to/drafts
#
# Dry run first: set DRY_RUN=1 to preview changes without writing.

DRAFTS_DIR="${1:?Usage: $0 /path/to/drafts}"
VAULT_PAGES="$HOME/notebook/pages"
DRY_RUN="${DRY_RUN:-1}"  # Default to dry run. Set DRY_RUN=0 to write.

if [ ! -d "$DRAFTS_DIR" ]; then
  echo "Error: $DRAFTS_DIR is not a directory"
  exit 1
fi

if [ ! -d "$VAULT_PAGES" ]; then
  echo "Error: $VAULT_PAGES is not a directory"
  exit 1
fi

SKIPPED=0
PROCESSED=0
COLLISIONS=0
ERRORS=0

find "$DRAFTS_DIR" -maxdepth 1 -name "*.md" -type f | sort | while IFS= read -r f; do
  BASE=$(basename "$f")

  # Skip files that already have frontmatter
  if head -1 "$f" | grep -q '^---'; then
    SKIPPED=$((SKIPPED + 1))
    if [ "$DRY_RUN" = "1" ]; then
      echo "SKIP (has frontmatter): $BASE"
    fi
    continue
  fi

  # Pre-flight collision check against entire vault
  EXISTING=$(find "$HOME/notebook" -name "$BASE" -type f ! -path "*/drafts/*" 2>/dev/null)
  if [ -n "$EXISTING" ]; then
    echo "COLLISION: $BASE already exists at $EXISTING — skipping"
    COLLISIONS=$((COLLISIONS + 1))
    continue
  fi

  # Extract date from filename (YYYY-MM-DD or YYYY_MM_DD at start of filename)
  CREATED=""
  DATE_FROM_NAME=$(echo "$BASE" | grep -oP '^\d{4}[-_]\d{2}[-_]\d{2}' | head -1 | tr '_' '-')
  if [ -n "$DATE_FROM_NAME" ]; then
    # Validate it's a real date
    if date -d "$DATE_FROM_NAME" +%Y-%m-%d >/dev/null 2>&1; then
      CREATED="$DATE_FROM_NAME"
    fi
  fi

  # Fall back to mtime if no date in filename
  if [ -z "$CREATED" ]; then
    EPOCH=$(stat --format='%Y' "$f" 2>/dev/null)
    if [ -n "$EPOCH" ] && [ "$EPOCH" != "0" ]; then
      CREATED=$(date -d "@$EPOCH" +%Y-%m-%d 2>/dev/null)
    fi
  fi

  # Build frontmatter
  FM="---
type: draft
status: filed
tags:
  - draft"
  if [ -n "$CREATED" ]; then
    FM="$FM
created: $CREATED"
  fi
  FM="$FM
---"

  if [ "$DRY_RUN" = "1" ]; then
    echo "WOULD PROCESS: $BASE  [created: ${CREATED:-unknown}] -> $VAULT_PAGES/$BASE"
  else
    # Prepend frontmatter and move to vault
    TMPFILE=$(mktemp)
    if printf '%s\n' "$FM" | cat - "$f" > "$TMPFILE" && mv "$TMPFILE" "$VAULT_PAGES/$BASE"; then
      echo "DONE: $BASE  [created: ${CREATED:-unknown}]"
      PROCESSED=$((PROCESSED + 1))
    else
      echo "ERROR: $BASE"
      ERRORS=$((ERRORS + 1))
      rm -f "$TMPFILE"
    fi
  fi

done

echo ""
echo "=== Summary ==="
if [ "$DRY_RUN" = "1" ]; then
  echo "DRY RUN — no files modified"
  echo "Run with DRY_RUN=0 to apply changes:"
  echo "  DRY_RUN=0 $0 $DRAFTS_DIR"
fi
echo "Skipped (already have frontmatter): $SKIPPED"
echo "Collisions (not moved): $COLLISIONS"
echo "Processed: $PROCESSED"
echo "Errors: $ERRORS"
