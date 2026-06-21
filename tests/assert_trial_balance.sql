select
    sum(dr_amount) - sum(cr_amount) as diff
from {{ ref('fct_journal_lines') }}
having abs(sum(dr_amount) - sum(cr_amount)) > 0.005
