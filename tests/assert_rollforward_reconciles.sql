-- Substantive control: ledger balance must equal the independently source-derived
-- expectation, per account. Offending rows = the break being caught.
select
    account_id,
    expected_ending,
    ledger_ending,
    expected_ending - ledger_ending as variance
from {{ ref('fct_balance_rollforward') }}
where abs(expected_ending - ledger_ending) > 0.005
