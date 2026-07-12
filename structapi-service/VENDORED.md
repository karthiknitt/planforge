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

Vendored at structapi tag: **v0.1.0**.
