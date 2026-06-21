select
    event_id,
    'payment'                              as event_type,
    loan_id,
    cast(event_date as date)               as event_date,
    cast(principal_amount as decimal(18,2)) as principal_amount,
    cast(interest_amount as decimal(18,2))  as interest_amount,
    cast(principal_amount + interest_amount as decimal(18,2)) as total_amount
from {{ ref('installment_payments') }}
