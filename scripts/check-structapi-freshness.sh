#!/usr/bin/env bash
# Weekly informational check: is structapi-service/VENDORED.md pinned to the
# LATEST tag on karthiknitt/structapi? If not, file (or update) a tracking
# issue. This does NOT fail the workflow — falling behind isn't a merge-time
# defect, just a heads-up to schedule a re-vendor.
set -euo pipefail

REPO="karthiknitt/structapi"
VENDORED_MD="structapi-service/VENDORED.md"

if [[ -z "${GH_TOKEN:-}" ]]; then
  echo "::warning::GH_TOKEN not set — skipping freshness check. Set STRUCTAPI_SYNC_TOKEN to enable."
  exit 0
fi

PINNED=$(grep -oE 'Vendored at structapi tag: \*\*(v[0-9A-Za-z.+-]+)\*\*' "$VENDORED_MD" \
         | grep -oE 'v[0-9A-Za-z.+-]+' || true)
LATEST=$(gh api "repos/$REPO/tags" --jq '.[0].name' 2>/dev/null || echo "")

echo "Pinned: ${PINNED:-?}   Latest: ${LATEST:-?}"

if [[ -z "$PINNED" || -z "$LATEST" || "$PINNED" == "$LATEST" ]]; then
  echo "Up to date (or could not determine a tag)."
  exit 0
fi

TITLE="structapi vendor is behind: pinned $PINNED, latest $LATEST"
BODY="The vendored copy in \`structapi-service/\` is pinned to **$PINNED**, but **$LATEST** is now available on [karthiknitt/structapi](https://github.com/$REPO/releases).

Refresh procedure: see \`structapi-service/VENDORED.md\`. After refreshing, the \`verify-structapi-vendor\` check will pass again.

_Opened automatically by the weekly vendor-freshness check._"

EXISTING=$(gh issue list --search "\"structapi vendor is behind\" in:title" --state open --json number -q '.[0].number' 2>/dev/null || echo "")

if [[ -n "$EXISTING" ]]; then
  gh issue comment "$EXISTING" --body "$BODY"
  echo "Updated existing issue #$EXISTING"
else
  gh issue create --title "$TITLE" --body "$BODY" \
    || gh issue create --title "$TITLE" --body "$BODY"
  echo "Opened new tracking issue"
fi
