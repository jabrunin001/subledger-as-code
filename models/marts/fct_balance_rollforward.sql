with movements as (
    select * from {{ ref('int_source_movements') }}
),
ledger as (
    select
        account_id,
        sum(dr_amount) - sum(cr_amount) as ledger_ending
    from {{ ref('fct_journal_lines') }}
    group by account_id
)
select
    m.account_id,
    cast(0 as decimal(18,2)) as beginning_balance,
    m.originations,
    m.principal_repayments,
    m.charge_offs,
    m.interest,
    cast(m.originations + m.principal_repayments + m.charge_offs + m.interest
         as decimal(18,2)) as expected_ending,
    cast(coalesce(l.ledger_ending, 0) as decimal(18,2)) as ledger_ending
from movements m
left join ledger l on m.account_id = l.account_id
