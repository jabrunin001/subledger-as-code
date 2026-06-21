select
    journal_line_id,
    journal_entry_id,
    event_id,
    event_type,
    loan_id,
    account_id,
    dr_amount,
    cr_amount,
    posted_at
from {{ ref('int_postings') }}
