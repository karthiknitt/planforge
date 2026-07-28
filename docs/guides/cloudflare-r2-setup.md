# Cloudflare R2 Setup for PlanForge

R2 stores generated artifacts (PDF, DXF, XLSX, AI render PNGs). Chosen over
GCS for two reasons: 10 GB free storage, and **zero egress fees** — egress is
the line item that bites at consumer scale.

## What needs configuring where

| System | Needed? | Why |
|---|---|---|
| **Cloudflare** | ✅ Yes | Bucket + API token live here |
| **GitHub Actions secrets** | ✅ Yes | Injected into Cloud Run by `deploy-backend.yml` |
| **gcloud / GCP** | ❌ **No** | R2 is not a GCP service. Nothing to configure. |
| **Vercel** | ❌ **No env vars** | Exports are generated in the backend; the frontend only follows a URL it is handed. |
| **Cloudflare CORS** | ⚠️ Only for `redirect` mode | If the browser fetches signed URLs directly, the bucket's CORS policy must list the Vercel origins. Configured on Cloudflare, not Vercel. |

## 1. Create the bucket

1. Cloudflare dashboard → **R2 Object Storage** → **Create bucket**
2. Name: `planforge-artifacts`
3. Location: **Automatic** (or APAC if most users are in India)
4. Leave public access **disabled** — access is via presigned URLs only

## 2. Note your Account ID

R2 overview page, right sidebar → **Account ID**. A 32-char hex string. The
S3 endpoint is derived from it:

    https://<your-account-id>.r2.cloudflarestorage.com

## 3. Create an API token

1. R2 → **Manage R2 API Tokens** → **Create API token**
2. Name: `planforge-backend`
3. Permission: **Object Read & Write**
4. Scope to the single bucket `planforge-artifacts` — not "all buckets"
5. TTL: leave as forever, or set a rotation reminder

Copy the **Access Key ID** and **Secret Access Key** immediately — the secret
is shown exactly once.

> ⚠️ **Do not paste these into any file in the repo, including markdown.**
> R2 keys were once committed to a status doc in this project and sat exposed
> for four months. They belong only in GitHub Actions secrets.

## 4. Store them as GitHub secrets

```bash
cd /home/karthik/projects/PlanForge

gh secret set R2_ACCOUNT_ID        --body '<your-account-id>'
gh secret set R2_ACCESS_KEY_ID     --body '<your-access-key-id>'
gh secret set R2_SECRET_ACCESS_KEY --body '<your-secret-access-key>'
gh secret set R2_BUCKET            --body 'planforge-artifacts'

gh secret list | grep R2
```

`deploy-backend.yml` passes all four to Cloud Run as env vars. Nothing is
stored in GCP Secret Manager, so there is no gcloud step.

## 5. Deploy and verify

Push to `main` (or run the workflow manually), then:

```bash
gcloud run services logs read planforge-backend --region=us-central1 --limit=100 \
  | grep -i "R2 not configured"
```

**No output = success.** The message "R2 not configured — artifacts stream
inline" means one of the four values is missing or empty.

Then export a PDF from the app and confirm the object appears:
Cloudflare → R2 → `planforge-artifacts` → an `exports/<project-id>/...` key.

## 6. (Later) Switching to redirect delivery

Default is `EXPORT_DELIVERY_MODE=inline` — the backend streams bytes, exactly
as before R2. Switching to `redirect` makes the backend 307 to a presigned
URL, so file bytes never pass through Cloud Run.

Before switching, add a CORS policy on the bucket:

```json
[
  {
    "AllowedOrigins": [
      "https://planforge-mauve.vercel.app",
      "http://localhost:3000"
    ],
    "AllowedMethods": ["GET"],
    "AllowedHeaders": ["*"],
    "MaxAgeSeconds": 3600
  }
]
```

Then set `EXPORT_DELIVERY_MODE=redirect` in `deploy-backend.yml` and redeploy.

**Gotcha:** a presigned URL must not receive an `Authorization` header — S3
rejects requests carrying two auth mechanisms. The Fetch spec strips
`Authorization` on cross-origin redirects, so browser `fetch` is safe, but a
server-side proxy that forwards headers manually is not. Test the download
path from the deployed frontend before considering this done.

## Cost expectations

| Item | Free tier | PlanForge scale |
|---|---|---|
| Storage | 10 GB/month | Well inside |
| Class A ops (writes) | 1,000,000/month | Well inside |
| Class B ops (reads) | 10,000,000/month | Well inside |
| **Egress** | **Unlimited, always free** | The reason R2 was chosen |
