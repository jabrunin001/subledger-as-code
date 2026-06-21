import csv
from pathlib import Path
from seed_events import generate

def _rows(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))

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
