select
    account_id,
    account_name,
    account_type,
    normal_balance
from {{ ref('chart_of_accounts') }}
