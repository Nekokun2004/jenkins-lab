#!/usr/bin/env bash
# Builds inventory/hosts.ini from `terraform output`.
# LocalStack Community instances are metadata only (not SSH-reachable), so the play targets
# localhost (the agent) with ansible_connection=local; the Terraform address is kept as a host var.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Fail loudly instead of writing a bogus inventory: a missing/empty Terraform output means nothing was applied.
if ! ADDRESS=$(cd "$HERE/../../terraform" && terraform output -no-color -raw instance_address 2>/dev/null) \
   || [[ ! "$ADDRESS" =~ ^[A-Za-z0-9._:-]+$ ]]; then
  echo "ERROR: terraform output instance_address is missing or malformed (was 'terraform apply' run against this state?)" >&2
  exit 1
fi
{
  echo "[taskflow]"
  echo "localhost ansible_connection=local terraform_reported_address=${ADDRESS}"
} > "$HERE/hosts.ini"
echo "Generated inventory — Terraform reported instance_address=${ADDRESS}"
echo "(LocalStack Community instances aren't reachable — targeting localhost, see Known Limitations)"
cat "$HERE/hosts.ini"
