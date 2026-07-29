# Solver service split — manual rollout steps

`deploy-solver.yml` adds a second Cloud Run service, `planforge-solver`, running
the **same image** as `planforge-backend` but sized for CP-SAT rather than API
traffic:

| | `planforge-backend` (API) | `planforge-solver` |
|---|---|---|
| concurrency | 4 | **1** — one solve per instance, no queuing behind a busy worker |
| cpu / memory | 1 / 1Gi | 2 / 2Gi |
| timeout | 300s | 600s |
| max instances | 3 | 5 |
| ingress | `--allow-unauthenticated` | `--allow-unauthenticated` |
| `INNGEST_APP_ID` | `planforge-api` | `planforge-solver` |

> **2026-07-29 incident:** this table originally read `--no-allow-unauthenticated`
> for the solver. That's unsatisfiable — Inngest Cloud is an external SaaS with
> no GCP identity, so it can never pass Cloud Run's IAM invoker check (confirmed:
> requests 403'd at the platform layer, before Inngest's own signature check ever
> ran). Every job routed to `planforge-solver` silently vanished; the only signal
> was the 120s queued-job watchdog in `jobs.py`. Fixed by granting `allUsers` the
> `roles/run.invoker` role (both live via `gcloud run services
> add-iam-policy-binding` and in `deploy-solver.yml` so it survives redeploys) —
> the same trust model `planforge-backend` already used: public ingress, real
> security enforced by `INNGEST_SIGNING_KEY` verification inside the Inngest SDK,
> not by Cloud Run IAM.

Cloud Run's free tier is **per project**, so two services draw from one pool —
splitting does not double the bill.

> **Prerequisite:** Task A1 (CP-SAT off the event loop) must be deployed first.
> Splitting a service whose loop still blocks just moves the problem.

---

## ⚠️ Read this before deploying: the app_id migration

Production currently runs with the **default** `INNGEST_APP_ID=planforge`
(`backend/app/config/settings.py`). This change renames the API service's app to
`planforge-api` and introduces `planforge-solver`.

That means after the first deploy Inngest will know about **three** app names:
the new `planforge-api`, the new `planforge-solver`, and the stale `planforge`
still holding the old function registrations.

This is the same failure class as PR #16, where two deployments shared one
`app_id` and jobs silently no-op'd against the wrong deployment. The symptom is
nasty: nothing errors, jobs just never run. Do not skip step 2.

---

## 1. Deploy both services

Merge to `main`. Both workflows trigger on `backend/**` and run concurrently —
that is expected. They build the same image tag; the solver reads the shared
`:buildcache` but deliberately does not write it, so the two concurrent builds
cannot corrupt each other's cache.

Confirm both services exist:

```bash
gcloud run services list --region=us-central1
```

## 2. Re-sync Inngest and retire the stale app

In the Inngest dashboard:

1. Sync the new solver app URL:
   `https://planforge-solver-<hash>-uc.a.run.app/api/inngest`
2. Sync the API app URL (its app name changed to `planforge-api`):
   `https://planforge-backend-<hash>-uc.a.run.app/api/inngest`
3. Confirm `layout/generate.requested` is registered under **`planforge-solver`**
   and **not** under `planforge-api`.
4. Archive/remove the stale `planforge` app once no functions remain under it.

Until step 3 is true, generation jobs may still be routed to the API service —
which works, but gives you none of the benefit of the split.

## 3. Verify end to end

Trigger a generation from the deployed frontend, then:

```bash
gcloud run services logs read planforge-solver --region=us-central1 --limit=50
```

Expected: solve logs on `planforge-solver`.

The actual acceptance test is the next one — **`/health` on
`planforge-backend` must stay responsive *during* a solve.** That is the entire
point of the split:

```bash
# while a generation is running
curl -s -o /dev/null -w '%{http_code} %{time_total}s\n' \
  https://<planforge-backend-url>/api/health
```

Expected: `200` with a fast response, concurrently with an in-flight solve.

## 4. Rollback

The split is config-only. To revert, delete `deploy-solver.yml`, remove the
`INNGEST_APP_ID=planforge-api` line from `deploy-backend.yml`, redeploy, and
re-sync Inngest against the single app. Then delete the service:

```bash
gcloud run services delete planforge-solver --region=us-central1
```
