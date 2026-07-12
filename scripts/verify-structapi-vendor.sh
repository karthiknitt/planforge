#!/usr/bin/env bash
# Verify planforge's vendored copy of structapi (structapi-service/) exactly
# matches the tag pinned in structapi-service/VENDORED.md. Run in CI on every
# change to structapi-service/**, and locally before committing a re-vendor.
#
# Requires: gh CLI with read access to karthiknitt/structapi (private repo).
# - Locally: `gh auth login` as an account with access is enough.
# - In CI: set GH_TOKEN to a fine-grained PAT (Contents: Read-only on
#   karthiknitt/structapi only) via the STRUCTAPI_SYNC_TOKEN secret. If unset,
#   this script SKIPS (warns) rather than failing, so the workflow doesn't
#   red-X before the secret is configured — see VENDORED.md for setup.
set -euo pipefail

REPO="karthiknitt/structapi"
VENDOR_DIR="structapi-service"
VENDORED_MD="$VENDOR_DIR/VENDORED.md"

if [[ -z "${GH_TOKEN:-}" ]]; then
  echo "::warning::GH_TOKEN not set — skipping vendor-sync verification. Set the STRUCTAPI_SYNC_TOKEN secret to enable this check (see $VENDORED_MD)."
  exit 0
fi

if [[ ! -f "$VENDORED_MD" ]]; then
  echo "::error::$VENDORED_MD not found"
  exit 1
fi

TAG=$(grep -oE 'Vendored at structapi tag: \*\*(v[0-9A-Za-z.+-]+)\*\*' "$VENDORED_MD" \
      | grep -oE 'v[0-9A-Za-z.+-]+' || true)
if [[ -z "$TAG" ]]; then
  echo "::error::Could not parse pinned tag from $VENDORED_MD (expected 'Vendored at structapi tag: **vX.Y.Z**')"
  exit 1
fi
echo "Pinned tag: $TAG"

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

echo "Cloning $REPO@$TAG ..."
gh repo clone "$REPO" "$WORK/structapi" -- --depth 1 --branch "$TAG" --quiet

SRC="$WORK/structapi/python"
STATUS=0

compare() {
  local rel="$1"
  if [[ ! -e "$SRC/$rel" ]]; then
    echo "::error::upstream missing $rel at tag $TAG"
    STATUS=1
    return
  fi
  if ! diff -r --strip-trailing-cr -x "__pycache__" -x "*.pyc" \
        "$SRC/$rel" "$VENDOR_DIR/$rel"; then
    echo "::error::vendored '$rel' differs from $REPO@$TAG"
    STATUS=1
  fi
}

compare iscodes
compare structapi
compare requirements.txt
compare requirements-api.txt

if [[ "$STATUS" -ne 0 ]]; then
  echo
  echo "Vendored copy is OUT OF SYNC with $REPO@$TAG."
  echo "Refresh it per $VENDORED_MD and commit, or re-pin the tag if this drift is intentional."
  exit 1
fi

echo "Vendored copy matches $REPO@$TAG exactly."
