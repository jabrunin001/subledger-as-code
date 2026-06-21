#!/usr/bin/env bash
# Proves the substantive control catches the break and the consistency checks don't.
set -uo pipefail

# Exclude unit tests so that the break propagates through all materialized models
# (without --exclude resource_type:unit_test, the unit test that expects 'interest_income'
#  fails first and causes downstream table models to be SKIPPED, leaving stale clean data).
dbt build --profiles-dir . --vars 'inject_break: true' \
  --exclude resource_type:unit_test >/dev/null 2>&1 || true

dbt test --profiles-dir . --vars 'inject_break: true' \
  --select assert_trial_balance assert_entries_balanced >/dev/null 2>&1
consistency=$?

dbt test --profiles-dir . --vars 'inject_break: true' \
  --select assert_rollforward_reconciles >/dev/null 2>&1
reconciliation=$?

if [ "$consistency" -eq 0 ] && [ "$reconciliation" -ne 0 ]; then
  echo "PASS: trial-balance/balanced GREEN, rollforward reconciliation RED (break caught)."
  exit 0
fi
echo "FAIL: expected consistency PASS ($consistency) and reconciliation FAIL ($reconciliation)."
exit 1
