select
    loan_id,
    borrower_id,
    cast(principal as decimal(18,2)) as principal,
    cast(apr as double)              as apr,
    cast(term_months as integer)     as term_months,
    cast(origination_date as date)   as origination_date
from {{ ref('loan_master') }}
