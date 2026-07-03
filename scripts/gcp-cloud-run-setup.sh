#!/usr/bin/env bash
# Phase 2 (Tasks 5-10) of docs/plans/2026-07-02-cloud-run-deployment-implementation-plan.md
# One-time GCP + Neon setup for the PlanForge backend Cloud Run deploy.
#
# Run as your own user - NOT with sudo. Every command here is a user-scoped
# gcloud call; sudo would create a root-owned gcloud config and break auth
# for every later gcloud/gh/GitHub-Actions call.
#
#   chmod +x scripts/gcp-cloud-run-setup.sh
#   ./scripts/gcp-cloud-run-setup.sh
#
# Safe to re-run: every step checks whether it already exists before creating.

set -uo pipefail

# ---- Config (override via env vars before running if you need different values) ----
PROJECT_ID="${PROJECT_ID:-thermal-well-451906-b0}"
REGION="${REGION:-us-central1}"
GITHUB_REPO="${GITHUB_REPO:-karthiknitt/planforge}"
SA_NAME="${SA_NAME:-planforge-deployer}"
AR_REPO="${AR_REPO:-planforge-backend}"
POOL_ID="${POOL_ID:-github-pool}"
PROVIDER_ID="${PROVIDER_ID:-github-provider}"
BUDGET_DISPLAY_NAME="${BUDGET_DISPLAY_NAME:-PlanForge \$0 tripwire}"
NEON_PROJECT_NAME="${NEON_PROJECT_NAME:-planforge}"
NEON_DB_NAME="${NEON_DB_NAME:-planforge}"
NEON_ROLE_NAME="${NEON_ROLE_NAME:-planforge_app}"
GH_REPO_SLUG="${GH_REPO_SLUG:-$GITHUB_REPO}"
BACKEND_ALLOWED_ORIGINS="${BACKEND_ALLOWED_ORIGINS:-https://planforge-mauve.vercel.app}"

OUT_FILE="$(dirname "$0")/../.gcp-cloud-run-setup.out"

# ---- Helpers ----
c_green() { printf '\033[0;32m%s\033[0m\n' "$1"; }
c_yellow() { printf '\033[0;33m%s\033[0m\n' "$1"; }
c_red() { printf '\033[0;31m%s\033[0m\n' "$1"; }
step() { printf '\n\033[1;36m== %s ==\033[0m\n' "$1"; }
die() { c_red "FATAL: $1"; exit 1; }

if [[ "${EUID}" -eq 0 ]]; then
  die "Do not run this with sudo/root. Re-run as your normal user."
fi

if ! command -v gcloud >/dev/null 2>&1; then
  c_yellow "gcloud CLI not found - installing to \$HOME/google-cloud-sdk (no sudo needed, it's a self-contained user-space install)..."
  curl -sSL https://sdk.cloud.google.com | bash -s -- --disable-prompts \
    || die "gcloud install failed - install manually: https://cloud.google.com/sdk/docs/install"
  export PATH="$HOME/google-cloud-sdk/bin:$PATH"
  command -v gcloud >/dev/null 2>&1 \
    || die "gcloud installed but not on PATH - open a new shell and re-run this script."
  c_green "gcloud installed: $(gcloud --version | head -1)"
  c_yellow "To make this permanent in new shells, add to ~/.zshrc:"
  echo '  export PATH="$HOME/google-cloud-sdk/bin:$PATH"'
fi

: > "$OUT_FILE"
echo "# Generated $(date -u +%Y-%m-%dT%H:%M:%SZ) by gcp-cloud-run-setup.sh" >> "$OUT_FILE"

# ============================================================
step "Task 5: Authenticate and set the active project"
# ============================================================
if gcloud auth list --filter="status:ACTIVE" --format="value(account)" 2>/dev/null | grep -q .; then
  c_green "Already authenticated as: $(gcloud auth list --filter='status:ACTIVE' --format='value(account)')"
else
  c_yellow "Opening browser for gcloud auth login (if Chromium already has an active Google session, it'll just ask you to pick the account and click Allow - no password re-entry)..."
  gcloud auth login || die "gcloud auth login failed"
fi

if gcloud projects describe "$PROJECT_ID" >/dev/null 2>&1; then
  c_green "Project '$PROJECT_ID' already exists - reusing it."
else
  read -r -p "Project '$PROJECT_ID' doesn't exist yet. Create it? [y/N] " ans
  if [[ "$ans" =~ ^[Yy]$ ]]; then
    gcloud projects create "$PROJECT_ID" --name="PlanForge" || die "project create failed"
  else
    read -r -p "Enter the existing GCP project ID to use instead: " PROJECT_ID
  fi
fi
gcloud config set project "$PROJECT_ID" || die "failed to set active project"

if gcloud billing projects describe "$PROJECT_ID" --format="value(billingEnabled)" 2>/dev/null | grep -qi true; then
  c_green "Billing already linked to '$PROJECT_ID'."
else
  c_yellow "Available billing accounts:"
  gcloud billing accounts list
  read -r -p "Paste the BILLING_ACCOUNT_ID to link (or leave blank to skip): " BILLING_ACCOUNT_ID
  if [[ -n "${BILLING_ACCOUNT_ID:-}" ]]; then
    gcloud billing projects link "$PROJECT_ID" --billing-account="$BILLING_ACCOUNT_ID" \
      || die "billing link failed"
  else
    c_yellow "Skipped billing link - Cloud Run/Artifact Registry calls will fail until you link billing."
  fi
fi
echo "PROJECT_ID=$PROJECT_ID" >> "$OUT_FILE"
echo "BILLING_ACCOUNT_ID=${BILLING_ACCOUNT_ID:-<not set, see above>}" >> "$OUT_FILE"

# ============================================================
step "Task 6: Enable required APIs"
# ============================================================
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  iamcredentials.googleapis.com \
  cloudbilling.googleapis.com \
  billingbudgets.googleapis.com \
  --project="$PROJECT_ID" \
  || die "enabling APIs failed"
c_green "APIs enabled."

# ============================================================
step "Task 7: Create the Artifact Registry repo with a cleanup policy"
# ============================================================
if gcloud artifacts repositories describe "$AR_REPO" --location="$REGION" --project="$PROJECT_ID" >/dev/null 2>&1; then
  c_green "Artifact Registry repo '$AR_REPO' already exists."
else
  gcloud artifacts repositories create "$AR_REPO" \
    --repository-format=docker \
    --location="$REGION" \
    --project="$PROJECT_ID" \
    --description="PlanForge backend images" \
    || die "artifact registry create failed"
fi

# A lone "Keep" policy is sufficient - Artifact Registry deletes anything not
# matched by a keep rule automatically. An unconditional "Delete" rule (no
# condition/mostRecentVersions key) is invalid and gcloud will reject it.
CLEANUP_POLICY_FILE="$(mktemp)"
cat > "$CLEANUP_POLICY_FILE" <<'EOF'
[
  {
    "name": "keep-recent-5",
    "action": {"type": "Keep"},
    "mostRecentVersions": {"keepCount": 5}
  }
]
EOF
gcloud artifacts repositories set-cleanup-policies "$AR_REPO" \
  --location="$REGION" \
  --project="$PROJECT_ID" \
  --policy="$CLEANUP_POLICY_FILE" \
  --no-dry-run \
  || c_yellow "Cleanup policy set failed/already set - check manually if this matters."
rm -f "$CLEANUP_POLICY_FILE"
c_green "Artifact Registry ready: ${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}"
echo "ARTIFACT_REGISTRY=${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}" >> "$OUT_FILE"

# ============================================================
step "Task 8: Create the Neon project and get connection strings"
# ============================================================
neon_manual_fallback() {
  c_yellow "Falling back to manual entry for the Neon connection string."
  echo "1. Open https://console.neon.tech and create a project named '$NEON_PROJECT_NAME'."
  echo "2. In Connection Details, copy the POOLED string (hostname ends -pooler)."
  echo "3. Swap its prefix: postgresql://...  ->  postgresql+asyncpg://..."
  read -r -p "Paste the converted (+asyncpg) pooled connection string here (or Enter to skip for now): " NEON_URL
  if [[ -n "${NEON_URL:-}" ]]; then
    echo "NEON_DATABASE_URL=$NEON_URL" >> "$OUT_FILE"
    c_green "Saved to $OUT_FILE (gitignored - never commit this)."
  else
    c_yellow "Skipped - fill in NEON_DATABASE_URL in $OUT_FILE manually before Task 11."
  fi
}

if ! command -v jq >/dev/null 2>&1; then
  c_yellow "jq not found (needed to parse neonctl's JSON output)."
  c_yellow "Install it yourself, then re-run: sudo apt-get install -y jq"
  neon_manual_fallback
else

if ! command -v neonctl >/dev/null 2>&1; then
  c_yellow "neonctl not found - installing (user-space, no sudo)..."
  if command -v bun >/dev/null 2>&1; then
    bun add -g neonctl || c_yellow "bun install of neonctl failed."
    export PATH="$(bun pm bin -g 2>/dev/null):$PATH"
  fi
  if ! command -v neonctl >/dev/null 2>&1 && command -v npm >/dev/null 2>&1; then
    npm i -g neonctl || c_yellow "npm install of neonctl failed."
  fi
  command -v neonctl >/dev/null 2>&1 || c_yellow "neonctl still not on PATH after install attempt."
fi

if ! command -v neonctl >/dev/null 2>&1; then
  c_red "neonctl unavailable - skipping automation for this step."
  neon_manual_fallback
else
  c_green "neonctl found: $(neonctl --version 2>/dev/null || echo unknown)"

  if neonctl projects list --output json >/dev/null 2>&1; then
    c_green "neonctl already authenticated."
  else
    c_yellow "Opening browser for 'neonctl auth' (uses your logged-in Chromium session if you have one)..."
    neonctl auth || c_yellow "neonctl auth did not complete - automation below may fail."
  fi

  NEON_PROJECT_ID="$(neonctl projects list --output json 2>/dev/null \
    | jq -r --arg name "$NEON_PROJECT_NAME" \
      'if type=="array" then . else (.projects // []) end
       | .[] | select(.name==$name) | .id' | head -1)"

  if [[ -n "${NEON_PROJECT_ID:-}" ]]; then
    c_green "Neon project '$NEON_PROJECT_NAME' already exists (id: $NEON_PROJECT_ID) - reusing it."
  else
    c_yellow "Creating Neon project '$NEON_PROJECT_NAME'..."
    CREATE_JSON="$(neonctl projects create \
      --name "$NEON_PROJECT_NAME" \
      --database "$NEON_DB_NAME" \
      --role "$NEON_ROLE_NAME" \
      --output json 2>&1)"
    if [[ $? -ne 0 ]]; then
      c_red "neonctl projects create failed:"
      echo "$CREATE_JSON"
      neon_manual_fallback
    else
      NEON_PROJECT_ID="$(echo "$CREATE_JSON" | jq -r \
        'if has("project") then .project.id else .id end' 2>/dev/null)"
    fi
  fi

  if [[ -n "${NEON_PROJECT_ID:-}" && "$NEON_PROJECT_ID" != "null" ]]; then
    NEON_URL="$(neonctl connection-string \
      --project-id "$NEON_PROJECT_ID" \
      --pooled \
      --database-name "$NEON_DB_NAME" \
      --role-name "$NEON_ROLE_NAME" 2>/dev/null)"
    if [[ -n "${NEON_URL:-}" ]]; then
      # asyncpg (unlike psycopg2) does not understand libpq-style query params.
      # SQLAlchemy's asyncpg dialect passes every URL query key straight
      # through as a kwarg to asyncpg.connect() (see create_connect_args in
      # sqlalchemy/dialects/postgresql/asyncpg.py: `opts.update(url.query)`).
      # asyncpg has no 'sslmode' or 'channel_binding' kwarg (-> TypeError), and
      # its 'ssl' kwarg, when given as a string, is parsed via SSLMode.parse()
      # which only accepts disable/allow/prefer/require/verify-ca/verify-full
      # (verified against the installed asyncpg's connect_utils.py) - so the
      # fix is renaming sslmode's value straight across to ssl=require, not
      # ssl=true. channel_binding has no asyncpg equivalent and is dropped;
      # Neon connections work fine without it (falls back to plain SCRAM).
      NEON_ASYNCPG_URL="$(echo "$NEON_URL" \
        | sed -E 's#^postgres(ql)?://#postgresql+asyncpg://#' \
        | sed -E 's/[?&](sslmode|channel_binding)=[^&]*//g' \
        | sed -E 's/\?&/?/; s/&&/\&/g')?ssl=require"
      c_green "Neon pooled connection string retrieved."
      {
        echo "NEON_PROJECT_ID=$NEON_PROJECT_ID"
        echo "NEON_DATABASE_URL=$NEON_ASYNCPG_URL"
      } >> "$OUT_FILE"
    else
      c_red "Could not retrieve connection string via neonctl."
      neon_manual_fallback
    fi
  else
    c_red "Could not determine Neon project id."
    neon_manual_fallback
  fi
fi
fi

# ============================================================
step "Task 9: Create the Workload Identity Federation trust + deploy service account"
# ============================================================
PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

if gcloud iam service-accounts describe "$SA_EMAIL" --project="$PROJECT_ID" >/dev/null 2>&1; then
  c_green "Service account '$SA_EMAIL' already exists."
else
  gcloud iam service-accounts create "$SA_NAME" \
    --display-name="PlanForge Cloud Run deployer" \
    --project="$PROJECT_ID" \
    || die "service account create failed"
fi

for role in roles/run.admin roles/artifactregistry.writer roles/iam.serviceAccountUser; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="$role" \
    --condition=None \
    >/dev/null \
    || c_yellow "IAM binding for $role may already exist - continuing."
done
c_green "IAM roles bound to $SA_EMAIL"

if gcloud iam workload-identity-pools describe "$POOL_ID" --location=global --project="$PROJECT_ID" >/dev/null 2>&1; then
  c_green "Workload Identity Pool '$POOL_ID' already exists."
else
  gcloud iam workload-identity-pools create "$POOL_ID" \
    --location="global" \
    --project="$PROJECT_ID" \
    --display-name="GitHub Actions pool" \
    || die "WIF pool create failed"
fi

if gcloud iam workload-identity-pools providers describe "$PROVIDER_ID" \
    --location=global --workload-identity-pool="$POOL_ID" --project="$PROJECT_ID" >/dev/null 2>&1; then
  c_green "WIF provider '$PROVIDER_ID' already exists - syncing its attribute-condition to \$GITHUB_REPO."
  # GitHub repo names are case-sensitive in GCP's CEL attribute-condition even
  # though GitHub itself treats them case-insensitively - always re-assert the
  # condition so a wrong-case GITHUB_REPO from an earlier run gets corrected.
  gcloud iam workload-identity-pools providers update-oidc "$PROVIDER_ID" \
    --location="global" \
    --workload-identity-pool="$POOL_ID" \
    --project="$PROJECT_ID" \
    --attribute-condition="assertion.repository=='${GITHUB_REPO}'" \
    || c_yellow "Could not update the WIF provider's attribute-condition - verify it matches '${GITHUB_REPO}' manually."
else
  gcloud iam workload-identity-pools providers create-oidc "$PROVIDER_ID" \
    --location="global" \
    --workload-identity-pool="$POOL_ID" \
    --project="$PROJECT_ID" \
    --display-name="GitHub OIDC provider" \
    --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
    --attribute-condition="assertion.repository=='${GITHUB_REPO}'" \
    --issuer-uri="https://token.actions.githubusercontent.com" \
    || die "WIF provider create failed"
fi

# add-iam-policy-binding is itself idempotent (re-applying the same binding is
# a safe no-op) - a failure here is a real error, not "already bound". The
# most common one is a fresh service account not yet propagated; retry once.
#
# Two DISTINCT roles are needed on the same WIF principal, not one:
#   - roles/iam.workloadIdentityUser lets the WIF principal exchange its GitHub
#     OIDC token for federated STS credentials "as" the service account. This
#     alone is enough for google-github-actions/auth@v3 and gcloud run deploy.
#   - roles/iam.serviceAccountTokenCreator lets it go further and actually
#     IMPERSONATE the service account to mint a real OAuth access token via
#     the IAM Credentials API's generateAccessToken. Docker's credential
#     helper (docker-credential-gcloud, used by `docker push`) needs this
#     second one specifically - missing it fails with exactly
#     "iam.serviceAccounts.getAccessToken denied", a step *after* auth@v3
#     itself has already succeeded, which is why it's easy to miss.
WIF_MEMBER="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL_ID}/attribute.repository/${GITHUB_REPO}"

bind_sa_role_for_wif() {
  local role="$1"
  local err_file
  err_file="$(mktemp)"
  if ! gcloud iam service-accounts add-iam-policy-binding "$SA_EMAIL" \
      --project="$PROJECT_ID" \
      --role="$role" \
      --member="$WIF_MEMBER" \
      >/dev/null 2>"$err_file"; then
    c_yellow "Binding $role failed - new service accounts can take ~60s to propagate. Waiting and retrying once..."
    sleep 60
    if ! gcloud iam service-accounts add-iam-policy-binding "$SA_EMAIL" \
        --project="$PROJECT_ID" \
        --role="$role" \
        --member="$WIF_MEMBER" \
        >/dev/null 2>"$err_file"; then
      c_red "Binding $role still failing - this is a real permission problem, not propagation delay:"
      cat "$err_file"
      c_yellow "Check your role on this project with:"
      echo "  gcloud projects get-iam-policy $PROJECT_ID --flatten=\"bindings[].members\" --filter=\"bindings.members:\$(gcloud config get-value account)\" --format=\"table(bindings.role)\""
      c_yellow "You need Owner or roles/iam.serviceAccountAdmin on '$PROJECT_ID' to grant this. Continuing script, but the deploy workflow will NOT work until this binding succeeds - re-run this script after fixing your role."
    else
      c_green "Binding $role succeeded on retry."
    fi
  else
    c_green "Bound $role to WIF principal."
  fi
  rm -f "$err_file"
}

bind_sa_role_for_wif "roles/iam.workloadIdentityUser"
bind_sa_role_for_wif "roles/iam.serviceAccountTokenCreator"

WIF_PROVIDER_NAME="$(gcloud iam workload-identity-pools providers describe "$PROVIDER_ID" \
  --location=global --workload-identity-pool="$POOL_ID" --project="$PROJECT_ID" \
  --format='value(name)')"

c_green "WIF provider: $WIF_PROVIDER_NAME"
c_green "Deploy service account: $SA_EMAIL"
{
  echo "GCP_WORKLOAD_IDENTITY_PROVIDER=$WIF_PROVIDER_NAME"
  echo "GCP_SERVICE_ACCOUNT=$SA_EMAIL"
} >> "$OUT_FILE"

# ============================================================
step "Task 10: Set a budget alert"
# ============================================================
BILLING_ACCOUNT_FOR_BUDGET="${BILLING_ACCOUNT_ID:-}"
if [[ -z "$BILLING_ACCOUNT_FOR_BUDGET" ]]; then
  gcloud billing accounts list
  read -r -p "Paste the BILLING_ACCOUNT_ID to attach the budget alert to: " BILLING_ACCOUNT_FOR_BUDGET
fi

if [[ -n "$BILLING_ACCOUNT_FOR_BUDGET" ]]; then
  # --quiet auto-answers any "API not enabled, enable it?" prompt instead of
  # blocking on stdin with the prompt text hidden by a 2>/dev/null redirect.
  existing="$(gcloud billing budgets list --billing-account="$BILLING_ACCOUNT_FOR_BUDGET" \
    --filter="displayName=\"$BUDGET_DISPLAY_NAME\"" --format='value(name)' --quiet)"
  if [[ -n "$existing" ]]; then
    c_green "Budget '$BUDGET_DISPLAY_NAME' already exists - skipping."
  else
    # No currency suffix on --budget-amount: per gcloud docs, a currency code
    # here must match the billing account's own currency or the API rejects
    # it with INVALID_ARGUMENT. Omitting it defaults to the account's native
    # currency (e.g. INR for an Indian account) - adjust BUDGET_AMOUNT below
    # if "1" isn't a meaningful tripwire threshold in your account's currency.
    gcloud billing budgets create \
      --billing-account="$BILLING_ACCOUNT_FOR_BUDGET" \
      --display-name="$BUDGET_DISPLAY_NAME" \
      --budget-amount="${BUDGET_AMOUNT:-1}" \
      --threshold-rule=percent=0.5 \
      --threshold-rule=percent=1.0 \
      --quiet \
      || c_yellow "Budget create failed - check the billing account ID."
  fi
else
  c_yellow "Skipped budget alert - no billing account ID given."
fi

# ============================================================
step "Task 11: GitHub secrets/variables + Vercel INTERNAL_AUTH_SECRET"
# ============================================================
out_val() { grep "^$1=" "$OUT_FILE" 2>/dev/null | tail -1 | cut -d= -f2-; }

if ! command -v gh >/dev/null 2>&1; then
  c_red "gh CLI not found - install it (https://cli.github.com) and re-run for Task 11."
else
  WIF_PROVIDER_FOR_SECRET="$(out_val GCP_WORKLOAD_IDENTITY_PROVIDER)"
  SA_EMAIL_FOR_SECRET="$(out_val GCP_SERVICE_ACCOUNT)"
  NEON_URL_FOR_SECRET="$(out_val NEON_DATABASE_URL)"

  if [[ -z "$WIF_PROVIDER_FOR_SECRET" || -z "$SA_EMAIL_FOR_SECRET" ]]; then
    c_red "Missing WIF provider / service account from Task 9 - skipping gh secret set for those."
  else
    gh secret set GCP_WORKLOAD_IDENTITY_PROVIDER --repo "$GH_REPO_SLUG" --body "$WIF_PROVIDER_FOR_SECRET" \
      && c_green "Set GCP_WORKLOAD_IDENTITY_PROVIDER" || c_yellow "Failed to set GCP_WORKLOAD_IDENTITY_PROVIDER"
    gh secret set GCP_SERVICE_ACCOUNT --repo "$GH_REPO_SLUG" --body "$SA_EMAIL_FOR_SECRET" \
      && c_green "Set GCP_SERVICE_ACCOUNT" || c_yellow "Failed to set GCP_SERVICE_ACCOUNT"
  fi

  if [[ -n "$NEON_URL_FOR_SECRET" ]]; then
    gh secret set NEON_DATABASE_URL --repo "$GH_REPO_SLUG" --body "$NEON_URL_FOR_SECRET" \
      && c_green "Set NEON_DATABASE_URL" || c_yellow "Failed to set NEON_DATABASE_URL"
  else
    c_yellow "No Neon connection string available - set NEON_DATABASE_URL manually before Task 13."
  fi

  gh secret set BACKEND_ALLOWED_ORIGINS --repo "$GH_REPO_SLUG" --body "$BACKEND_ALLOWED_ORIGINS" \
    && c_green "Set BACKEND_ALLOWED_ORIGINS" || c_yellow "Failed to set BACKEND_ALLOWED_ORIGINS"

  gh variable set GCP_PROJECT_ID --repo "$GH_REPO_SLUG" --body "$PROJECT_ID" \
    && c_green "Set GCP_PROJECT_ID variable" || c_yellow "Failed to set GCP_PROJECT_ID variable"
  gh variable set GCP_REGION --repo "$GH_REPO_SLUG" --body "$REGION" \
    && c_green "Set GCP_REGION variable" || c_yellow "Failed to set GCP_REGION variable"

  # INTERNAL_AUTH_SECRET is a shared HS256 key: the Next.js proxy signs, FastAPI
  # verifies. Both GitHub secrets and Vercel env vars are write-only (no API
  # reads the value back), so this can only be generated ONCE and pushed to
  # both places together - regenerating on a re-run would silently desync
  # whichever side already has last time's value.
  GH_HAS_SECRET=false
  if gh secret list --repo "$GH_REPO_SLUG" --json name -q '.[].name' 2>/dev/null | grep -qx "INTERNAL_AUTH_SECRET"; then
    GH_HAS_SECRET=true
  fi
  VERCEL_HAS_SECRET=false
  if command -v vercel >/dev/null 2>&1 && vercel env ls production 2>/dev/null | grep -q "INTERNAL_AUTH_SECRET"; then
    VERCEL_HAS_SECRET=true
  fi

  if $GH_HAS_SECRET && $VERCEL_HAS_SECRET; then
    c_green "INTERNAL_AUTH_SECRET already set on both GitHub and Vercel - leaving it alone."
  elif $GH_HAS_SECRET && ! $VERCEL_HAS_SECRET; then
    c_red "INTERNAL_AUTH_SECRET exists on GitHub but NOT on Vercel production."
    c_yellow "Can't recover GitHub's value to sync it (secrets are write-only). Either delete the GitHub secret and re-run to regenerate both in sync, or set Vercel's INTERNAL_AUTH_SECRET manually to match it."
  elif ! $GH_HAS_SECRET && $VERCEL_HAS_SECRET; then
    c_red "INTERNAL_AUTH_SECRET exists on Vercel production but NOT on GitHub."
    c_yellow "Can't recover Vercel's value to sync it (env vars are write-only). Either remove the Vercel var and re-run to regenerate both in sync, or set GitHub's secret manually to match it."
  elif ! command -v openssl >/dev/null 2>&1; then
    c_red "openssl not found - generate a secret yourself (e.g. 'openssl rand -hex 32') and set it manually on both GitHub and Vercel."
  else
    NEW_INTERNAL_AUTH_SECRET="$(openssl rand -hex 32)"
    if gh secret set INTERNAL_AUTH_SECRET --repo "$GH_REPO_SLUG" --body "$NEW_INTERNAL_AUTH_SECRET"; then
      c_green "Set INTERNAL_AUTH_SECRET on GitHub (newly generated)."
      if ! command -v vercel >/dev/null 2>&1; then
        c_yellow "vercel CLI not found - set INTERNAL_AUTH_SECRET manually in Vercel production to: $NEW_INTERNAL_AUTH_SECRET"
      elif printf '%s' "$NEW_INTERNAL_AUTH_SECRET" | vercel env add INTERNAL_AUTH_SECRET production; then
        c_green "Set INTERNAL_AUTH_SECRET on Vercel production (matches GitHub)."
      else
        c_yellow "Vercel set failed - set it manually in Vercel production to: $NEW_INTERNAL_AUTH_SECRET"
      fi
    else
      c_yellow "Failed to set INTERNAL_AUTH_SECRET on GitHub."
    fi
  fi
fi

# ============================================================
step "Phase 2 + Task 11 complete"
# ============================================================
c_green "Summary saved to: $OUT_FILE (gitignored, do not commit)"
echo
cat "$OUT_FILE"
echo
c_yellow "Next: Task 13 - push a throwaway branch and trigger deploy-backend.yml."
