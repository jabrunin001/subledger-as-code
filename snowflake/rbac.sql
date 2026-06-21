-- Least-privilege role hierarchy for the subledger (SOX segregation of duties).
-- Apply once as an account admin before running dbt against the `snowflake` target.

create role if not exists subledger_reader;     -- read-only analytics consumers
create role if not exists subledger_transformer; -- dbt service role (build models)
create role if not exists auditor_ro;            -- auditors: read-only, PII always masked

grant usage on warehouse subledger_wh to role subledger_transformer;
grant usage on database subledger to role subledger_transformer;
grant usage on schema subledger.analytics to role subledger_transformer;
grant create table on schema subledger.analytics to role subledger_transformer;
grant create view on schema subledger.analytics to role subledger_transformer;

grant usage on database subledger to role subledger_reader;
grant usage on schema subledger.analytics to role subledger_reader;
grant select on all tables in schema subledger.analytics to role subledger_reader;
grant select on future tables in schema subledger.analytics to role subledger_reader;

-- auditor_ro = read-only like subledger_reader; borrower PII is always masked for this role (see masking_policies.sql).
grant role subledger_reader to role auditor_ro;
