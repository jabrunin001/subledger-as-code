select
    event_id,
    'charge_off'                   as event_type,
    loan_id,
    cast(event_date as date)       as event_date,
    cast(amount as decimal(18,2))  as principal_amount,
    cast(0 as decimal(18,2))       as interest_amount,
    cast(amount as decimal(18,2))  as total_amount
from {{ ref('charge_offs') }}
