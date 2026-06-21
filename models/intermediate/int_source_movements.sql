-- Independent, hand-encoded expected double-entry derived straight from source events.
-- This bypasses posting_rules / post_entry on purpose: it is the "source of truth"
-- the ledger is reconciled against. Signed convention: debit positive, credit negative.
with orig as (
    select sum(principal_amount) as p from {{ ref('stg_originations') }}
),
pay as (
    select sum(principal_amount) as pp, sum(interest_amount) as ii from {{ ref('stg_payments') }}
),
co as (
    select sum(total_amount) as a from {{ ref('stg_charge_offs') }}
),
movements as (
    -- loans_receivable: +originations, -principal repayments, -charge-offs
    select 'loans_receivable' as account_id,
           coalesce((select p from orig), 0)  as originations,
           -coalesce((select pp from pay), 0) as principal_repayments,
           -coalesce((select a from co), 0)   as charge_offs,
           cast(0 as decimal(18,2))           as interest
    union all
    -- cash: -originations (disbursed), +principal repaid, +interest received
    select 'cash',
           -coalesce((select p from orig), 0),
           coalesce((select pp from pay), 0),
           cast(0 as decimal(18,2)),
           coalesce((select ii from pay), 0)
    union all
    -- interest_income: credit-normal, -interest
    select 'interest_income',
           cast(0 as decimal(18,2)),
           cast(0 as decimal(18,2)),
           cast(0 as decimal(18,2)),
           -coalesce((select ii from pay), 0)
    union all
    -- charge_off_expense: +charge-offs
    select 'charge_off_expense',
           cast(0 as decimal(18,2)),
           cast(0 as decimal(18,2)),
           coalesce((select a from co), 0),
           cast(0 as decimal(18,2))
)
select
    account_id,
    cast(originations as decimal(18,2))         as originations,
    cast(principal_repayments as decimal(18,2)) as principal_repayments,
    cast(charge_offs as decimal(18,2))          as charge_offs,
    cast(interest as decimal(18,2))             as interest
from movements
