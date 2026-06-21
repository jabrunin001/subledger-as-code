"""Deterministic synthetic BNPL event generator.

Simple per-installment interest: each month principal repays principal/term and
interest accrues on the declining outstanding balance at apr/12. A fixed RNG seed
makes regeneration byte-identical.
"""
import argparse
import csv
import os
import random
from datetime import date, timedelta

N_LOANS = 50
TERM_MONTHS = 12

def _round(x: float) -> float:
    return round(x + 1e-9, 2)

def generate(out_dir: str) -> dict[str, int]:
    os.makedirs(out_dir, exist_ok=True)
    rng = random.Random(42)

    loans, originations, payments, charge_offs = [], [], [], []

    for i in range(N_LOANS):
        loan_id = f"L{i:04d}"
        borrower_id = f"B{i % 37:04d}"
        principal = float(rng.randrange(50000, 300000)) / 100.0  # $500 to $3000
        apr = rng.choice([0.0, 0.10, 0.15, 0.22])
        start = date(2026, 1, 1) + timedelta(days=i)

        loans.append({
            "loan_id": loan_id, "borrower_id": borrower_id,
            "principal": _round(principal), "apr": apr,
            "term_months": TERM_MONTHS, "origination_date": start.isoformat(),
        })
        originations.append({
            "event_id": f"ORIG-{loan_id}", "loan_id": loan_id,
            "principal": _round(principal), "event_date": start.isoformat(),
        })

        # How far this loan progresses: fully paid, partially paid, or charged off.
        outcome = rng.random()
        n_paid = TERM_MONTHS if outcome > 0.4 else rng.randint(1, TERM_MONTHS - 1)
        will_charge_off = outcome <= 0.15

        outstanding = _round(principal)
        monthly_principal = principal / TERM_MONTHS
        for m in range(1, n_paid + 1):
            is_last_payment = m == n_paid
            is_settling = is_last_payment and not will_charge_off
            if is_settling:
                # Final payment on a fully-paid loan: absorb the exact remaining
                # balance so the per-loan principal invariant holds to the cent.
                pay_principal = outstanding
            else:
                pay_principal = _round(min(monthly_principal, outstanding))
            interest = _round(outstanding * (apr / 12.0))
            outstanding = _round(outstanding - pay_principal)
            pay_date = start + timedelta(days=30 * m)
            payments.append({
                "event_id": f"PAY-{loan_id}-{m:02d}", "loan_id": loan_id,
                "principal_amount": pay_principal,
                "interest_amount": interest,
                "event_date": pay_date.isoformat(),
            })

        if will_charge_off and outstanding > 0:
            co_date = start + timedelta(days=30 * (n_paid + 1))
            charge_offs.append({
                "event_id": f"CO-{loan_id}", "loan_id": loan_id,
                "amount": _round(outstanding), "event_date": co_date.isoformat(),
            })

    _write(out_dir, "loan_master.csv",
           ["loan_id", "borrower_id", "principal", "apr", "term_months", "origination_date"], loans)
    _write(out_dir, "loan_originations.csv",
           ["event_id", "loan_id", "principal", "event_date"], originations)
    _write(out_dir, "installment_payments.csv",
           ["event_id", "loan_id", "principal_amount", "interest_amount", "event_date"], payments)
    _write(out_dir, "charge_offs.csv",
           ["event_id", "loan_id", "amount", "event_date"], charge_offs)

    return {"loan_master": len(loans), "loan_originations": len(originations),
            "installment_payments": len(payments), "charge_offs": len(charge_offs)}

def _write(out_dir: str, name: str, fieldnames: list[str], rows: list[dict]) -> None:
    with open(os.path.join(out_dir, name), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="seeds/raw")
    args = ap.parse_args()
    print(generate(args.out))
