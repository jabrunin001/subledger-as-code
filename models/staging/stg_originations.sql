select
    event_id,
    'origination'                  as event_type,
    loan_id,
    cast(event_date as date)       as event_date,
    cast(principal as decimal(18,2)) as principal_amount,
    cast(0 as decimal(18,2))         as interest_amount,
    cast(principal as decimal(18,2)) as total_amount
from {{ ref('loan_originations') }}
