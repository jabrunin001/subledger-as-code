with events as (
    select * from {{ ref('stg_originations') }}
    union all
    select * from {{ ref('stg_payments') }}
    union all
    select * from {{ ref('stg_charge_offs') }}
),

{{ post_entry('events', ref('posting_rules')) }}
