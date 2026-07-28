# Neon pooled endpoint

In the Neon console, project `planforge` (`plain-brook-17631682`), copy the
**Pooled connection** string — its host contains `-pooler`. Then:

```bash
gh secret set NEON_DATABASE_URL --body '<pooled-connection-string>'
```

Re-deploy the backend. Check Cloud Run logs for the "not Neon's pooled
endpoint" warning — its absence confirms the change took effect.
