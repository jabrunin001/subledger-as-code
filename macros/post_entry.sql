{% macro post_entry(events_cte, rules_ref) %}

__rules as (
    select * from {{ rules_ref }}
),

__joined as (
    select
        e.event_id,
        e.event_type,
        e.loan_id,
        e.event_date as posted_at,
        r.leg,
        r.dr_cr,
        -- inject_break: route payment interest to 'cash' instead of 'interest_income'.
        -- The entry stays balanced (still a credit of the same amount), so only the
        -- substantive source-to-ledger reconciliation can detect it.
        {% if var('inject_break', false) %}
        case
            when r.event_type = 'payment' and r.amount_source = 'interest' then 'cash'
            else r.account_id
        end as account_id,
        {% else %}
        r.account_id as account_id,
        {% endif %}
        case r.amount_source
            when 'principal' then e.principal_amount
            when 'interest'  then e.interest_amount
            when 'total'     then e.total_amount
        end as amount
    from {{ events_cte }} e
    join __rules r on e.event_type = r.event_type
)

select
    event_id || '-' || cast(leg as varchar)        as journal_line_id,
    event_id                                        as journal_entry_id,
    event_id,
    event_type,
    loan_id,
    account_id,
    cast(case when dr_cr = 'debit'  then amount else 0 end as decimal(18,2)) as dr_amount,
    cast(case when dr_cr = 'credit' then amount else 0 end as decimal(18,2)) as cr_amount,
    posted_at
from __joined

{% endmacro %}
