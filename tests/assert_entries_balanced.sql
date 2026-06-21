-- Returns offending entries; an empty result = test passes.
select
    journal_entry_id,
    sum(dr_amount) - sum(cr_amount) as diff
from {{ ref('fct_journal_lines') }}
group by journal_entry_id
having abs(sum(dr_amount) - sum(cr_amount)) > 0.005
