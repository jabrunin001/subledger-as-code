{{
  config(
    materialized = 'table',
    meta = {
      'dbt_metricflow': {
        'time_spine': {
          'date_column': 'date_day',
          'granularity': 'day'
        }
      }
    }
  )
}}

select cast(range_date as date) as date_day
from range(date '2020-01-01', date '2031-01-01', interval 1 day)
