"""Phase 03: inventory is ledger-backed. Every batch quantity change writes one stock movement."""

import sqlite3
from datetime import date, timedelta

import pytest

from .conftest import auth

TODAY = date.today()


def iso(days: int) -> str:
    return (TODAY + timedelta(days=days)).isoformat()


@pytest.fixture
def api(demo_client, manager, db_path):
    headers = auth(manager)
    pid = manager["_pharmacy_id"]

    class Api:
        pharmacy_id = pid

        def get(self, path):
            return demo_client.get("/api/v1" + path, headers=headers)

        def post(self, path, body=None):
            return demo_client.post("/api/v1" + path, headers=headers, json=body)

        def put(self, path, body):
            return demo_client.put("/api/v1" + path, headers=headers, json=body)

        def delete(self, path):
            return demo_client.delete("/api/v1" + path, headers=headers)

        def sql(self, query, *args):
            conn = sqlite3.connect(db_path)
            try:
                return conn.execute(query, args).fetchall()
            finally:
                conn.close()

        def medicine(self, sku, batches, price="10.00", **extra):
            first, *rest = batches
            response = self.post("/inventory/medicines", {"pharmacy_id": pid, "sku": sku, "name": f"Synthetic {sku}",
                                                          "unit_price": price, "reorder_level": 5, **extra,
                                                          "initial_batch": first})
            assert response.status_code == 201, response.text
            medicine = response.json()
            for batch in rest:
                assert self.post(f"/inventory/medicines/{medicine['id']}/batches", batch).status_code == 201
            return medicine

        def batch(self, medicine_id, number):
            return self.sql("SELECT id, quantity FROM stock_batches WHERE medicine_id = ? AND batch_number = ?", medicine_id, number)[0]

        def movements(self, medicine_id):
            return self.sql(
                "SELECT m.movement_type, m.quantity_delta, m.quantity_after, b.batch_number, m.source_type, m.source_id, m.reason "
                "FROM stock_movements m JOIN stock_batches b ON b.id = m.batch_id WHERE m.medicine_id = ? ORDER BY m.id",
                medicine_id,
            )

        def ledger_balances(self):
            """Batches whose quantity differs from the sum of their movements (should be none)."""
            return self.sql(
                "SELECT b.id, b.quantity, COALESCE(SUM(m.quantity_delta), 0) FROM stock_batches b "
                "LEFT JOIN stock_movements m ON m.batch_id = b.id GROUP BY b.id "
                "HAVING b.quantity != COALESCE(SUM(m.quantity_delta), 0)"
            )

    return Api()


def batch_spec(number, qty, days=365):
    return {"batch_number": number, "expiry_date": iso(days), "quantity": qty}


def test_create_and_update_product(api):
    med = api.medicine("SYN-A", [batch_spec("A1", 12)])
    assert api.movements(med["id"]) == [("receipt", 12, 12, "A1", "batch", api.batch(med["id"], "A1")[0], None)]
    assert api.put(f"/inventory/medicines/{med['id']}", {"name": "Synthetic A renamed", "reorder_level": 3}).status_code == 200
    assert api.sql("SELECT name, version FROM medicines WHERE id = ?", med["id"]) == [("Synthetic A renamed", 2)]
    assert len(api.movements(med["id"])) == 1, "editing a product does not move stock"
    current = api.get(f"/inventory/medicines/{med['id']}").json()
    assert current["quantity_on_hand"] == 12 and current["nearest_expiry"] == iso(365)


def test_receipt_increase_and_reduction_write_movements(api):
    med = api.medicine("SYN-B", [batch_spec("B1", 10)])
    assert api.post(f"/inventory/medicines/{med['id']}/batches", batch_spec("B2", 20, 500)).status_code == 201
    b2, qty = api.batch(med["id"], "B2")
    assert qty == 20

    up = api.post(f"/inventory/batches/{b2}/adjust", {"quantity_delta": 5, "reason": "Count correction"})
    down = api.post(f"/inventory/batches/{b2}/adjust", {"quantity_delta": -8, "reason": "Damaged strips"})
    assert up.status_code == 200 and down.status_code == 200
    assert api.batch(med["id"], "B2")[1] == 17
    assert api.movements(med["id"])[1:] == [
        ("receipt", 20, 20, "B2", "batch", b2, None),
        ("adjustment", 5, 25, "B2", "adjustment", None, "Count correction"),
        ("adjustment", -8, 17, "B2", "adjustment", None, "Damaged strips"),
    ]
    assert api.get(f"/inventory/medicines/{med['id']}").json()["quantity_on_hand"] == 27
    assert api.ledger_balances() == []


def test_adjustment_needs_reason_and_non_zero_delta(api):
    med = api.medicine("SYN-C", [batch_spec("C1", 5)])
    b1, _ = api.batch(med["id"], "C1")
    for body in ({"quantity_delta": 1}, {"quantity_delta": 1, "reason": "   "}, {"quantity_delta": 0, "reason": "x"}):
        assert api.post(f"/inventory/batches/{b1}/adjust", body).status_code == 422, body
    assert len(api.movements(med["id"])) == 1


def test_adjustment_below_zero_rolls_back(api):
    med = api.medicine("SYN-D", [batch_spec("D1", 4)])
    b1, _ = api.batch(med["id"], "D1")
    before = api.sql("SELECT COUNT(*) FROM stock_movements")[0][0]
    response = api.post(f"/inventory/batches/{b1}/adjust", {"quantity_delta": -5, "reason": "Too many"})
    assert response.status_code == 400
    assert api.batch(med["id"], "D1")[1] == 4
    assert api.sql("SELECT COUNT(*) FROM stock_movements")[0][0] == before
    assert api.sql("SELECT COUNT(*) FROM audit_logs WHERE action = 'batch.adjusted'") == [(0,)]


def test_database_refuses_negative_batch_quantity(api):
    med = api.medicine("SYN-E", [batch_spec("E1", 1)])
    with pytest.raises(sqlite3.IntegrityError):
        api.sql("UPDATE stock_batches SET quantity = -1 WHERE medicine_id = ?", med["id"])


def test_sale_takes_earliest_expiry_writes_movements_and_void_restores(api):
    med = api.medicine("SYN-F", [batch_spec("LATE", 10, 400), batch_spec("SOON", 3, 60), batch_spec("OLD", 5, -1)])
    late, soon, old = (api.batch(med["id"], n)[0] for n in ("LATE", "SOON", "OLD"))
    sale = api.post("/billing/sales", {"pharmacy_id": api.pharmacy_id, "items": [{"medicine_id": med["id"], "quantity": 5}]})
    assert sale.status_code == 201, sale.text
    sale_id = sale.json()["id"]

    assert [api.batch(med["id"], n)[1] for n in ("LATE", "SOON", "OLD")] == [8, 0, 5], "expired OLD untouched"
    sale_moves = [m for m in api.movements(med["id"]) if m[0] == "sale"]
    assert sale_moves == [("sale", -3, 0, "SOON", "sale", sale_id, None), ("sale", -2, 8, "LATE", "sale", sale_id, None)]

    assert api.post(f"/billing/sales/{sale_id}/void", {"reason": "Returned"}).status_code == 200
    assert [api.batch(med["id"], n)[1] for n in ("LATE", "SOON", "OLD")] == [10, 3, 5]
    void_moves = [m for m in api.movements(med["id"]) if m[0] == "void"]
    assert sorted(void_moves, key=lambda m: m[3]) == [("void", 2, 10, "LATE", "sale", sale_id, None), ("void", 3, 3, "SOON", "sale", sale_id, None)]
    assert api.ledger_balances() == []


def test_dispense_writes_dispense_movements(api):
    med = api.medicine("SYN-G", [batch_spec("G1", 6)])
    patient = api.post("/patients/", {"pharmacy_id": api.pharmacy_id, "first_name": "Ledger", "last_name": "Synthetic", "phone": "0300-1"}).json()
    rx = api.post("/prescriptions/", {"pharmacy_id": api.pharmacy_id, "patient_id": patient["id"],
                                      "items": [{"medicine_id": med["id"], "quantity": 4}]}).json()
    assert api.post(f"/prescriptions/{rx['id']}/dispense").status_code == 200
    assert api.movements(med["id"])[-1] == ("dispense", -4, 2, "G1", "prescription", rx["id"], None)


def test_short_stock_sale_or_dispense_leaves_no_partial_change(api):
    plenty = api.medicine("SYN-H", [batch_spec("H1", 50)])
    scarce = api.medicine("SYN-I", [batch_spec("I1", 2)])
    moves_before = api.sql("SELECT COUNT(*) FROM stock_movements")[0][0]

    sale = api.post("/billing/sales", {"pharmacy_id": api.pharmacy_id, "items": [
        {"medicine_id": plenty["id"], "quantity": 10}, {"medicine_id": scarce["id"], "quantity": 3}]})
    assert sale.status_code == 400
    assert api.batch(plenty["id"], "H1")[1] == 50, "first line must not be decremented"
    assert api.sql("SELECT COUNT(*) FROM stock_movements")[0][0] == moves_before
    assert api.sql("SELECT COUNT(*) FROM sales") == [(0,)]

    patient = api.post("/patients/", {"pharmacy_id": api.pharmacy_id, "first_name": "Short", "last_name": "Synthetic", "phone": "0300-2"}).json()
    rx = api.post("/prescriptions/", {"pharmacy_id": api.pharmacy_id, "patient_id": patient["id"], "items": [
        {"medicine_id": plenty["id"], "quantity": 10}, {"medicine_id": scarce["id"], "quantity": 3}]}).json()
    assert api.post(f"/prescriptions/{rx['id']}/dispense").status_code == 400
    assert api.batch(plenty["id"], "H1")[1] == 50
    assert api.sql("SELECT COUNT(*) FROM stock_movements")[0][0] == moves_before
    assert api.sql("SELECT status, version FROM prescriptions WHERE id = ?", rx["id"]) == [("recorded", 1)]


def test_history_endpoint_is_chronological_and_stable(api):
    med = api.medicine("SYN-J", [batch_spec("J1", 9)])
    j1, _ = api.batch(med["id"], "J1")
    for delta in (1, -2, 3):
        api.post(f"/inventory/batches/{j1}/adjust", {"quantity_delta": delta, "reason": f"step {delta}"})
    first = api.get(f"/inventory/medicines/{med['id']}/movements")
    second = api.get(f"/inventory/medicines/{med['id']}/movements")
    assert first.status_code == 200 and first.json() == second.json()
    history = first.json()
    assert [(m["movement_type"], m["quantity_delta"], m["quantity_after"]) for m in history] == [
        ("receipt", 9, 9), ("adjustment", 1, 10), ("adjustment", -2, 8), ("adjustment", 3, 11)]
    assert [m["id"] for m in history] == sorted(m["id"] for m in history)
    assert all(m["batch_number"] == "J1" and m["staff_name"] == "Test Manager" for m in history)
    assert all(m["created_at"].endswith(("Z", "+00:00")) for m in history), "times are labelled UTC"
    assert all(len(m["public_id"]) == 36 for m in history)
    assert api.get("/inventory/medicines/999999/movements").status_code == 404


def test_search_and_low_stock_still_match(api):
    med = api.medicine("SYN-LOW", [batch_spec("L1", 3)], barcode="999000111")
    by_name = [m["id"] for m in api.get(f"/inventory/medicines?pharmacy_id={api.pharmacy_id}&search=SYN-LOW").json()]
    by_barcode = [m["id"] for m in api.get(f"/inventory/medicines?pharmacy_id={api.pharmacy_id}&search=999000111").json()]
    low = api.get(f"/inventory/medicines?pharmacy_id={api.pharmacy_id}&low_stock=true").json()
    assert by_name == [med["id"]] and by_barcode == [med["id"]]
    assert med["id"] in [m["id"] for m in low]
    l1, _ = api.batch(med["id"], "L1")
    api.post(f"/inventory/batches/{l1}/adjust", {"quantity_delta": 10, "reason": "Delivery counted"})
    low = api.get(f"/inventory/medicines?pharmacy_id={api.pharmacy_id}&low_stock=true").json()
    assert med["id"] not in [m["id"] for m in low], "low-stock follows the ledger-backed quantity"


def test_medicine_with_stock_history_cannot_be_deleted(api):
    med = api.medicine("SYN-K", [batch_spec("K1", 1)])
    response = api.delete(f"/inventory/medicines/{med['id']}")
    assert response.status_code == 409
    assert "stock history" in response.json()["detail"]
    assert api.sql("SELECT COUNT(*) FROM medicines WHERE id = ?", med["id"]) == [(1,)]


def test_demo_seed_and_whole_flow_keep_ledger_balanced(api):
    # Demo seed batches arrive as receipts, so every batch balances from the start.
    assert api.sql("SELECT COUNT(*) FROM stock_movements WHERE source_type = 'seed'")[0][0] > 0
    assert api.ledger_balances() == []
