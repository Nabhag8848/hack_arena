#!/usr/bin/env bash
# Wipe local experiment outputs + HydraDB tenant data for a fresh start.
set -euo pipefail
cd "$(dirname "$0")"
source .venv/bin/activate

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

echo "=== Clearing local experiment outputs ==="
rm -rf experiments/outputs/*
mkdir -p experiments/outputs
rm -f .hydradb_seeded

tenant="${HYDRA_DB_TENANT:-${APPWORLD_EXPERIMENT:-team_nabhag}}"
if [[ -n "${HYDRA_DB_API_KEY:-}" && "${HYDRA_DB_ENABLED:-1}" == "1" ]]; then
  echo "=== Resetting HydraDB tenants (keeping default-tenant) ==="
  python -u - <<PY
from hydra_db import HydraDB
import os

client = HydraDB(token=os.environ["HYDRA_DB_API_KEY"])
primary = os.environ.get("HYDRA_DB_TENANT") or os.environ.get("APPWORLD_EXPERIMENT", "team_nabhag")
listed = client.tenants.list()
for tid in listed.data.tenant_ids:
    if tid == "default-tenant":
        continue
    if tid == primary or tid.startswith("team_nabhag"):
        resp = client.tenants.delete(tenant_id=tid)
        msg = resp.data.message if resp.data else resp
        print(f"  deleted {tid}: {msg}")
remaining = client.tenants.list().data.tenant_ids
print(f"  remaining tenants: {remaining}")
PY
else
  echo "HydraDB disabled or no API key — skipped remote cleanup"
fi

cat <<EOF

✅ Reset complete.
  - experiments/outputs/ is empty
  - .hydradb_seeded removed (API docs will re-seed on next run)
  - HydraDB tenant "$tenant" will be recreated on next agent run

Next: bash run.sh smoke
EOF
