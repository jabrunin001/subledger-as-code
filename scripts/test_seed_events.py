import csv
from pathlib import Path
from seed_events import generate

def _rows(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))

def _headers(path):
    with open(path, newline="") as f:
        reader = csv.reader(f)
        return next(reader)

def test_generate_is_deterministic_and_balanced(tmp_path):
    counts = generate(str(tmp_path))
    assert counts["loan_master"] == 50

    # Every payment splits into principal + interest, both non-negative.
    payments = _rows(tmp_path / "installment_payments.csv")
    assert len(payments) > 0
    for p in payments:
        assert float(p["principal_amount"]) >= 0
        assert float(p["interest_amount"]) >= 0

    # Determinism: a second run into a fresh dir is byte-identical.
    second = tmp_path / "second"
    second.mkdir()
    generate(str(second))
    for name in ["loan_master", "loan_originations", "installment_payments", "charge_offs"]:
        a = (tmp_path / f"{name}.csv").read_bytes()
        b = (second / f"{name}.csv").read_bytes()
        assert a == b, f"{name}.csv not deterministic"


def test_csv_headers(tmp_path):
    generate(str(tmp_path))

    expected = {
        "loan_master.csv": ["loan_id", "borrower_id", "principal", "apr", "term_months", "origination_date"],
        "loan_originations.csv": ["event_id", "loan_id", "principal", "event_date"],
        "installment_payments.csv": ["event_id", "loan_id", "principal_amount", "interest_amount", "event_date"],
        "charge_offs.csv": ["event_id", "loan_id", "amount", "event_date"],
    }
    for fname, cols in expected.items():
        actual = _headers(tmp_path / fname)
        assert actual == cols, f"{fname} headers mismatch: {actual!r} != {cols!r}"


def test_row_counts(tmp_path):
    generate(str(tmp_path))

    loans = _rows(tmp_path / "loan_master.csv")
    originations = _rows(tmp_path / "loan_originations.csv")
    charge_offs_rows = _rows(tmp_path / "charge_offs.csv")

    assert len(loans) == 50
    assert len(originations) == len(loans), "loan_originations count must equal loan_master count"
    assert len(charge_offs_rows) >= 1, "charge_offs.csv must have at least 1 row"


def test_principal_invariant(tmp_path):
    """For every loan, origination principal - sum(payment principal_amount) - charge_off amount == 0."""
    generate(str(tmp_path))

    loans = {r["loan_id"]: float(r["principal"]) for r in _rows(tmp_path / "loan_master.csv")}
    payments = _rows(tmp_path / "installment_payments.csv")
    charge_offs = {r["loan_id"]: float(r["amount"]) for r in _rows(tmp_path / "charge_offs.csv")}

    # Sum payment principals per loan
    paid_principal: dict[str, float] = {}
    for p in payments:
        lid = p["loan_id"]
        paid_principal[lid] = paid_principal.get(lid, 0.0) + float(p["principal_amount"])

    for loan_id, orig_principal in loans.items():
        paid = paid_principal.get(loan_id, 0.0)
        co = charge_offs.get(loan_id, 0.0)
        residual = orig_principal - paid - co
        assert abs(residual) < 0.005, (
            f"{loan_id}: principal={orig_principal}, paid={paid:.2f}, "
            f"charge_off={co:.2f}, residual={residual:.4f}"
        )
