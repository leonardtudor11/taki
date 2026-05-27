#!/usr/bin/env bash
# V7.28 — Idempotent Cloud Run deploy for the Taki backend.
#
# What this does:
#   1. Generates TAKI_AUTH_TOKEN if not in .env (random hex), appends to .env
#   2. Pushes BRIGHTDATA_API_KEY + TAKI_AUTH_TOKEN to Secret Manager
#   3. Grants Cloud Run runtime SA: roles/aiplatform.user + secretAccessor
#   4. Deploys via `gcloud run deploy --source .` (Buildpacks + Dockerfile)
#   5. Prints the public URL + a one-line smoke test command
#
# Re-run after any code change — gcloud rebuilds the image incrementally.
#
# Env knobs:
#   SERVICE   default: taki-backend
#   REGION    default: us-central1
#
# Prereqs (all should already be enabled — see docs/RESUME.md):
#   - gcloud configured (project + auth)
#   - billing active
#   - APIs enabled: run, cloudbuild, artifactregistry, secretmanager, aiplatform
#   - .env at repo root with BRIGHTDATA_API_KEY + GCP_PROJECT_ID

set -euo pipefail
cd "$(dirname "$0")/.."

SERVICE="${SERVICE:-taki-backend}"
REGION="${REGION:-us-central1}"
PROJECT="$(gcloud config get-value project)"

say() { printf '\n\033[1;36m→ %s\033[0m\n' "$*"; }
ok()  { printf '\033[1;32m✓ %s\033[0m\n' "$*"; }
err() { printf '\033[1;31m✗ %s\033[0m\n' "$*" >&2; }

# ── 0. sanity check ──────────────────────────────────────────────────
[ -f .env ] || { err ".env missing"; exit 1; }
[ -f Dockerfile ] || { err "Dockerfile missing"; exit 1; }

for k in BRIGHTDATA_API_KEY GCP_PROJECT_ID; do
  grep -qE "^${k}=" .env || { err "$k missing from .env"; exit 1; }
done

# ── 1. ensure TAKI_AUTH_TOKEN exists ────────────────────────────────
if ! grep -qE "^TAKI_AUTH_TOKEN=" .env; then
  say "generating TAKI_AUTH_TOKEN"
  TOKEN="$(openssl rand -hex 16)"
  printf '\nTAKI_AUTH_TOKEN=%s\n' "$TOKEN" >> .env
  ok "wrote TAKI_AUTH_TOKEN to .env"
fi

# shellcheck disable=SC2046
export $(grep -vE '^(#|\s*$)' .env | xargs)

# ── 2. push secrets to Secret Manager ───────────────────────────────
say "pushing secrets to Secret Manager"
for secret in BRIGHTDATA_API_KEY TAKI_AUTH_TOKEN; do
  val="${!secret:-}"
  [ -z "$val" ] && continue
  if gcloud secrets describe "$secret" --project="$PROJECT" >/dev/null 2>&1; then
    printf '%s' "$val" | gcloud secrets versions add "$secret" \
      --data-file=- --project="$PROJECT" --quiet >/dev/null
  else
    printf '%s' "$val" | gcloud secrets create "$secret" \
      --data-file=- --project="$PROJECT" \
      --replication-policy=automatic --quiet >/dev/null
  fi
  ok "secret: $secret"
done

# ── 3. IAM bindings on the Cloud Run runtime SA ─────────────────────
say "wiring runtime SA permissions"
PROJECT_NUM="$(gcloud projects describe "$PROJECT" --format='value(projectNumber)')"
RUNTIME_SA="${PROJECT_NUM}-compute@developer.gserviceaccount.com"

for role in \
    roles/aiplatform.user \
    roles/secretmanager.secretAccessor \
    roles/storage.objectViewer \
    roles/artifactregistry.writer \
    roles/logging.logWriter \
    roles/cloudbuild.builds.builder \
    ; do
  gcloud projects add-iam-policy-binding "$PROJECT" \
    --member="serviceAccount:${RUNTIME_SA}" \
    --role="$role" --quiet >/dev/null
  ok "role: $role"
done

# ── 4. deploy ───────────────────────────────────────────────────────
say "deploying $SERVICE to $REGION"
gcloud run deploy "$SERVICE" \
  --source . \
  --region "$REGION" \
  --project "$PROJECT" \
  --allow-unauthenticated \
  --port 8080 \
  --memory 2Gi \
  --cpu 1 \
  --timeout 600 \
  --concurrency 4 \
  --min-instances 0 \
  --max-instances 2 \
  --set-env-vars "GCP_PROJECT_ID=${GCP_PROJECT_ID},GCP_LOCATION=${GCP_LOCATION:-global},BRIGHTDATA_SERP_ZONE=${BRIGHTDATA_SERP_ZONE:-},BRIGHTDATA_UNLOCKER_ZONE=${BRIGHTDATA_UNLOCKER_ZONE:-},TAKI_BD_SPEND_CAP=${TAKI_BD_SPEND_CAP:-10}" \
  --set-secrets "BRIGHTDATA_API_KEY=BRIGHTDATA_API_KEY:latest,TAKI_AUTH_TOKEN=TAKI_AUTH_TOKEN:latest" \
  --quiet

URL="$(gcloud run services describe "$SERVICE" --region="$REGION" --format='value(status.url)')"

# ── 5. wire frontend/api.json so Vercel uses this backend ───────────
if [ -f frontend/api.json ]; then
  say "updating frontend/api.json with backend URL"
  .venv/bin/python <<PY
import json, pathlib
p = pathlib.Path("frontend/api.json")
cfg = json.loads(p.read_text())
cfg["backend_base"] = "${URL}"
p.write_text(json.dumps(cfg, indent=2) + "\n")
PY
  ok "frontend/api.json → backend_base=${URL}"
  echo "  next: cd frontend && npx vercel --prod --yes"
fi

echo
ok "deployed: $URL"
echo
echo "  smoke test (status — no auth needed):"
echo "    curl -s ${URL}/api/status | head -c 200"
echo
echo "  smoke test (live run — needs ?key=\$TAKI_AUTH_TOKEN):"
echo "    curl -X POST '${URL}/api/run?key=${TAKI_AUTH_TOKEN}' \\"
echo "      -H 'Content-Type: application/json' \\"
echo "      -d '{\"mode\":\"demo\"}'"
echo
echo "  share with judges:"
echo "    https://frontend-sage-pi.vercel.app/?key=${TAKI_AUTH_TOKEN}"
