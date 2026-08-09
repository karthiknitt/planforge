# structapi (vendored copy)

**Source of truth: https://github.com/karthiknitt/structapi** (`python/iscodes`
+ `python/structapi`). This copy exists only because Cloud Run deploys must
run from THIS repo's GitHub Actions (the Workload Identity Federation
provider's attribute condition is `assertion.repository=='karthiknitt/planforge'`),
and this repo's `GITHUB_TOKEN` cannot check out the private structapi repo.

- Deployed by `.github/workflows/deploy-structapi.yml` (push to main touching
  `structapi-service/**`, or manual dispatch) to Cloud Run service `structapi`.
- **Do not edit here.** Make changes in the structapi repo (its CI runs the
  81-test suite incl. the v1 contract-freeze golden), then refresh this copy:

```bash
# from the planforge repo root, with the structapi repo cloned as a sibling
rm -rf structapi-service/iscodes structapi-service/structapi
cp -r ../structapi/python/iscodes ../structapi/python/structapi structapi-service/
cp ../structapi/python/requirements.txt ../structapi/python/requirements-api.txt structapi-service/
find structapi-service -name __pycache__ -type d -exec rm -rf {} +
```

Vendored at structapi tag: **v0.4.0**.

## CI enforcement (drift detection)

`.github/workflows/verify-structapi-vendor.yml` guarantees this copy can
never silently drift from the pinned tag above:

- **On every push/PR touching `structapi-service/**`**: `scripts/verify-structapi-vendor.sh`
  clones `karthiknitt/structapi` at the pinned tag and byte-diffs
  `iscodes/`, `structapi/`, `requirements.txt`, `requirements-api.txt`
  against this directory. Any difference fails the check with the diff
  printed inline.
- **Weekly (Mondays 06:00 UTC)**: `scripts/check-structapi-freshness.sh`
  compares the pinned tag against structapi's latest tag and files (or
  updates) a tracking issue if this copy is behind — informational only,
  does not fail.

### One-time setup: `STRUCTAPI_SYNC_TOKEN`

Both scripts need read access to the **private** `karthiknitt/structapi`
repo from the Actions runner (which only has a `GITHUB_TOKEN` scoped to
`planforge`). Without the secret, both checks **soft-skip with a warning**
instead of failing — the workflow won't red-X until you set it up:

1. Create a fine-grained PAT at
   https://github.com/settings/personal-access-tokens/new
   - Resource owner: `karthiknitt`
   - Repository access: **Only select repositories** → `structapi`
   - Permissions: **Contents: Read-only** (nothing else)
   - Expiration: set a reminder to rotate it
2. `gh secret set STRUCTAPI_SYNC_TOKEN --repo karthiknitt/planforge --body '<paste token>'`

Run the same check locally any time with `bash scripts/verify-structapi-vendor.sh`
(uses your own `gh auth login` session — no token env needed).
