#!/usr/bin/env bash
# Proves the deterministic triage explains the caught break: classifies it
# wrong_account and names the cash / interest_income accounts.
set -uo pipefail

# Rebuild with the break so fct_balance_rollforward holds the variance.
# Exclude unit tests (they assert the *correct* posting and would otherwise halt the
# build before the break reaches the materialized tables).
dbt build --profiles-dir . --vars 'inject_break: true' \
  --exclude resource_type:unit_test >/dev/null 2>&1 || true

out=$(python -m audit_cli.cli triage --backend heuristic 2>/dev/null)
echo "$out"

if echo "$out" | grep -qi "wrong_account" \
   && echo "$out" | grep -qi "cash" \
   && echo "$out" | grep -qi "interest_income"; then
  echo "PASS: triage classified the break as wrong_account on cash/interest_income."
  exit 0
fi
echo "FAIL: triage did not classify the break as expected."
exit 1
