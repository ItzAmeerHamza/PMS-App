"""Phase 05: prescriptions — create, history, scope, dispense, offline, restart."""

import socket
import sqlite3
from datetime import date, timedelta

import pytest

from .conftest import auth, start_client


@pytest.fixture
def rx(demo_client, manager, db_path):
    headers = auth(manager)
    pid = manager["_pharmacy_id"]

    class Rx:
        pharmacy_id = pid
        client = demo_client
        hdrs = headers

        def get(self, path, client=None):
            return (client or demo_client).get("/api/v1" + path, headers=headers)

        def post(self, path, body=None, client=None):
            return (client or demo_client).post("/api/v1" + path, headers=headers, json=body)

        def put(self, path, body):
            return demo_client.put("/api/v1" + path, headers=headers, json=body)

        def sql(self, query, *args, write=False):
            conn = sqlite3.connect(db_path)
            try:
                rows = conn.execute(query, args).fetchall()
                if write:
                    conn.commit()
                return rows
            finally:
                conn.close()

        def patient(self, first="Rx", phone="0300-7770001"):
            response = self.post("/patients/", {"pharmacy_id": pid, "first_name": first, "last_name": "Synthetic", "phone": phone})
            assert response.status_code == 201, response.text
            return response.json()

        def medicine(self, sku, qty=20, days=365, **extra):
            response = self.post("/inventory/medicines", {
                "pharmacy_id": pid, "sku": sku, "name": f"Synthetic {sku}", "salt": f"Salt {sku}",
                "manufacturer": "Synthetic Labs", "unit_price": "5.00", **extra,
                "initial_batch": {"batch_number": f"{sku}-B1", "expiry_date": (date.today() + timedelta(days=days)).isoformat(), "quantity": qty},
            })
            assert response.status_code == 201, response.text
            return response.json()

        def create(self, patient_id, items, **extra):
            return self.post("/prescriptions/", {"pharmacy_id": pid, "patient_id": patient_id, "items": items, **extra})

        def snapshot(self, prescription_id):
            return (
                self.sql("SELECT patient_id, doctor_name, complaint, diagnosis, notes, status, prescribed_at, version "
                         "FROM prescriptions WHERE id = ?", prescription_id),
                self.sql("SELECT medicine_id, medicine_name, medicine_salt, medicine_company, dosage, frequency, "
                         "duration_days, quantity, instructions FROM prescription_items WHERE prescription_id = ? ORDER BY id",
                         prescription_id),
            )

    return Rx()


LINE_A = {"dosage": "500 mg", "frequency": "1-0-1", "duration_days": 5, "quantity": 10, "instructions": "After meals"}
LINE_B = {"dosage": "10 mg", "frequency": "0-0-1", "duration_days": 7, "quantity": 7, "instructions": "At night"}


def test_prescription_with_two_items_is_stored(rx):
    patient = rx.patient()
    a, b = rx.medicine("RXA"), rx.medicine("RXB")
    response = rx.create(patient["id"], [{"medicine_id": a["id"], **LINE_A}, {"medicine_id": b["id"], **LINE_B}],
                         doctor_name="Dr Synthetic", complaint="Synthetic cough", diagnosis="Synthetic diagnosis")
    assert response.status_code == 201, response.text
    created = response.json()
    assert created["status"] == "recorded" and len(created["items"]) == 2
    _, items = rx.snapshot(created["id"])
    assert items == [
        (a["id"], "Synthetic RXA", "Salt RXA", "Synthetic Labs", "500 mg", "1-0-1", 5, 10, "After meals"),
        (b["id"], "Synthetic RXB", "Salt RXB", "Synthetic Labs", "10 mg", "0-0-1", 7, 7, "At night"),
    ]
    assert all(len(public_id) == 36 for (public_id,) in rx.sql("SELECT public_id FROM prescription_items WHERE prescription_id = ?", created["id"]))


def test_second_prescription_and_catalog_edits_leave_the_first_unchanged(rx):
    patient = rx.patient()
    med = rx.medicine("RXC")
    first = rx.create(patient["id"], [{"medicine_id": med["id"], **LINE_A}], diagnosis="First visit").json()
    before = rx.snapshot(first["id"])

    second = rx.create(patient["id"], [{"medicine_id": med["id"], **LINE_B}], diagnosis="Second visit")
    assert second.status_code == 201
    rx.put(f"/inventory/medicines/{med['id']}", {"name": "Renamed in catalog", "manufacturer": "Other Labs"})

    assert rx.snapshot(first["id"]) == before, "history is not rewritten"
    assert rx.get(f"/prescriptions/{first['id']}").json()["items"][0]["medicine_name"] == "Synthetic RXC"
    assert rx.sql("SELECT COUNT(*) FROM prescriptions WHERE patient_id = ?", patient["id"]) == [(2,)]


def test_patient_history_is_chronological_and_stable(rx):
    patient = rx.patient()
    med = rx.medicine("RXD")
    ids = [rx.create(patient["id"], [{"medicine_id": med["id"], "quantity": 1}], diagnosis=f"Visit {n}").json()["id"] for n in range(3)]
    path = f"/prescriptions/?pharmacy_id={rx.pharmacy_id}&patient_id={patient['id']}"

    oldest_first = rx.get(path + "&order=asc").json()
    assert [r["id"] for r in oldest_first] == ids
    times = [r["prescribed_at"] for r in oldest_first]
    assert times == sorted(times) and len(set(times)) == 3, "visits in the same second still get distinct times"
    assert [r["id"] for r in rx.get(path + "&order=asc").json()] == ids
    assert [r["id"] for r in rx.get(path).json()] == ids[::-1], "default list is newest first"
    assert rx.get(path + "&order=sideways").status_code == 422


def test_other_pharmacy_medicine_patient_and_prescription_are_rejected(rx):
    patient = rx.patient()
    other = rx.post("/pharmacies/", {"name": "Other Synthetic Pharmacy"}).json()["id"]
    rx.sql("INSERT INTO medicines (public_id, pharmacy_id, sku, name, unit_price, reorder_level, is_active, version) "
           "VALUES ('00000000-0000-4000-8000-0000000000c1', ?, 'OTHER-1', 'Other pharmacy medicine', 1, 1, 1, 1)", other, write=True)
    rx.sql("INSERT INTO patients (public_id, pharmacy_id, first_name, last_name, phone, version) "
           "VALUES ('00000000-0000-4000-8000-0000000000c2', ?, 'Other', 'Synthetic', '0300-7779999', 1)", other, write=True)
    their_med = rx.sql("SELECT id FROM medicines WHERE sku = 'OTHER-1'")[0][0]
    their_patient = rx.sql("SELECT id FROM patients WHERE pharmacy_id = ?", other)[0][0]
    rx.sql("INSERT INTO prescriptions (public_id, pharmacy_id, patient_id, status, version) "
           "VALUES ('00000000-0000-4000-8000-0000000000c3', ?, ?, 'recorded', 1)", other, their_patient, write=True)
    their_rx = rx.sql("SELECT id FROM prescriptions WHERE pharmacy_id = ?", other)[0][0]
    count = rx.sql("SELECT COUNT(*) FROM prescriptions")[0][0]

    assert rx.create(patient["id"], [{"medicine_id": their_med, "quantity": 1}]).status_code == 400
    assert rx.create(their_patient, [{"medicine_id": rx.medicine("RXE")["id"], "quantity": 1}]).status_code == 400
    assert rx.post("/prescriptions/", {"pharmacy_id": other, "patient_id": their_patient,
                                       "items": [{"medicine_id": their_med, "quantity": 1}]}).status_code == 403
    assert rx.sql("SELECT COUNT(*) FROM prescriptions")[0][0] == count, "nothing written"

    assert rx.get(f"/prescriptions/?pharmacy_id={other}").status_code == 403
    assert their_rx not in [r["id"] for r in rx.get(f"/prescriptions/?pharmacy_id={rx.pharmacy_id}").json()]
    assert rx.get(f"/prescriptions/{their_rx}").status_code == 404
    assert rx.post(f"/prescriptions/{their_rx}/cancel").status_code == 404
    assert rx.post(f"/prescriptions/{their_rx}/dispense").status_code == 404
    assert rx.sql("SELECT status FROM prescriptions WHERE id = ?", their_rx) == [("recorded",)]


def test_invalid_prescriptions_are_rejected(rx):
    patient = rx.patient()
    med = rx.medicine("RXF")
    inactive = rx.medicine("RXG", is_active=False)
    assert rx.create(patient["id"], []).status_code == 400
    assert rx.create(patient["id"], [{"medicine_id": inactive["id"], "quantity": 1}]).status_code == 400
    assert rx.create(patient["id"], [{"medicine_id": med["id"], "quantity": 0}]).status_code == 422
    assert rx.create(patient["id"], [{"medicine_id": med["id"], "quantity": 1, "duration_days": 0}]).status_code == 422
    assert rx.create(patient["id"], [{"medicine_id": med["id"], "quantity": 1, "dosage": "x" * 101}]).status_code == 422
    assert rx.sql("SELECT COUNT(*) FROM prescriptions WHERE patient_id = ?", patient["id"]) == [(0,)]


def test_dispense_with_enough_stock_writes_movements(rx):
    patient = rx.patient()
    med = rx.medicine("RXH", qty=6)
    created = rx.create(patient["id"], [{"medicine_id": med["id"], "quantity": 4}]).json()
    response = rx.post(f"/prescriptions/{created['id']}/dispense")
    assert response.status_code == 200 and response.json()["status"] == "dispensed" and response.json()["dispensed_at"]
    assert rx.sql("SELECT movement_type, quantity_delta, quantity_after, source_type, source_id FROM stock_movements "
                  "WHERE medicine_id = ? ORDER BY id", med["id"])[-1] == ("dispense", -4, 2, "prescription", created["id"])
    assert rx.post(f"/prescriptions/{created['id']}/cancel").status_code == 400, "cancelling a dispensed prescription stays forbidden"


def test_dispense_without_enough_stock_rolls_back(rx):
    patient = rx.patient()
    plenty, scarce = rx.medicine("RXI", qty=30), rx.medicine("RXJ", qty=1)
    created = rx.create(patient["id"], [{"medicine_id": plenty["id"], "quantity": 5}, {"medicine_id": scarce["id"], "quantity": 2}]).json()
    movements = rx.sql("SELECT COUNT(*) FROM stock_movements")[0][0]
    assert rx.post(f"/prescriptions/{created['id']}/dispense").status_code == 400
    assert rx.sql("SELECT status, version, dispensed_at FROM prescriptions WHERE id = ?", created["id"]) == [("recorded", 1, None)]
    assert rx.sql("SELECT SUM(quantity) FROM stock_batches WHERE medicine_id = ?", plenty["id"]) == [(30,)]
    assert rx.sql("SELECT COUNT(*) FROM stock_movements")[0][0] == movements


def test_works_with_no_cloud_host_and_no_network(rx, monkeypatch):
    monkeypatch.delenv("CLOUD_API_URL", raising=False)

    def blocked(*_args, **_kwargs):
        raise OSError("network disabled for this test")

    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)

    patient = rx.patient(first="Offline", phone="0300-7770077")
    found = rx.get(f"/patients/?pharmacy_id={rx.pharmacy_id}&search=Offline").json()
    assert [p["id"] for p in found] == [patient["id"]]
    med = rx.medicine("RXOFF", qty=10)
    created = rx.create(patient["id"], [{"medicine_id": med["id"], "quantity": 2}])
    assert created.status_code == 201
    batch = med["batches"][0]["id"]
    adjusted = rx.post(f"/inventory/batches/{batch}/adjust", {"quantity_delta": -1, "reason": "Offline count"})
    assert adjusted.status_code == 200 and adjusted.json()["quantity"] == 9
    assert rx.post(f"/prescriptions/{created.json()['id']}/dispense").status_code == 200


def test_rows_survive_an_api_restart(rx):
    patient = rx.patient(first="Restart", phone="0300-7770088")
    med = rx.medicine("RXR", qty=8)
    created = rx.create(patient["id"], [{"medicine_id": med["id"], **LINE_A, "quantity": 3}]).json()
    rx.post(f"/inventory/batches/{med['batches'][0]['id']}/adjust", {"quantity_delta": 2, "reason": "Delivery"})
    rx.client.__exit__(None, None, None)  # stop the first app instance

    with start_client() as fresh:
        token = fresh.post("/api/v1/auth/login", json={"username": "test-manager", "password": "correct horse 42"}).json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        again = fresh.get(f"/api/v1/prescriptions/{created['id']}", headers=headers).json()
        assert again["items"][0]["dosage"] == "500 mg" and again["patient_name"] == "Restart Synthetic"
        stock = fresh.get(f"/api/v1/inventory/medicines/{med['id']}", headers=headers).json()
        assert stock["quantity_on_hand"] == 10
        history = fresh.get(f"/api/v1/inventory/medicines/{med['id']}/movements", headers=headers).json()
        assert [m["movement_type"] for m in history] == ["receipt", "adjustment"]
