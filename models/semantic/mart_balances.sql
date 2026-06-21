select
    j.account_id,
    a.account_name,
    a.account_type,
    cast(sum(j.dr_amount) - sum(j.cr_amount) as decimal(18,2)) as balance,
    cast(min(j.posted_at) as date) as ds
from {{ ref('fct_journal_lines') }} j
join {{ ref('dim_account') }} a on j.account_id = a.account_id
group by j.account_id, a.account_name, a.account_type
