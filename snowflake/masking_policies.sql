-- Column-level masking so auditors (auditor_ro) never see raw borrower PII,
-- while the transformer role retains full access for reconciliation.

create masking policy if not exists mask_borrower as (val string)
  returns string ->
    case
      when current_role() in ('SUBLEDGER_TRANSFORMER') then val
      else 'MASKED'
    end;

alter table subledger.analytics.dim_loan
  modify column borrower_id set masking policy mask_borrower;
