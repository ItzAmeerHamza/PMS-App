"""Phase 04: patients — create, search, repeat visitors, history-preserving removal, pharmacy scope."""

import logging
import sqlite3

import pytest

from .conftest import auth

AYESHA = {"first_name": "Ayesha", "last_name": "Synthetica", "phone": "0300-5550101", "allergies": "Synthetic penicillin", "notes": "Synthetic note"}
BILAL = {"first_name": "Bilal", "last_name": "Fakename", "phone": "0300-5550202"}


@pytest.fixture
def ctx(demo_client, manager, db_path):
    headers = auth(manager)
    pid = manager["_pharmacy_id"]

    class Ctx:
        pharmacy_id = pid
        client = demo_client

        def get(self, path):
            return demo_client.get("/api/v1" + path, headers=headers)

        def post(self, path, body=None):
            return demo_client.post("/api/v1" + path, headers=headers, json=body)

        def put(self, path, body):
            return demo_client.put("/api/v1" + path, headers=headers, json=body)

        def delete(self, path):
            return demo_client.delete("/api/v1" + path, headers=headers)

        def sql(self, query, *args, write=False):
            conn = sqlite3.connect(db_path)
            try:
                rows = conn.execute(query, args).fetchall()
                if write:
                    conn.commit()
                return rows
            finally:
                conn.close()

        def patient(self, data):
            response = self.post("/patients/", {"pharmacy_id": pid, **data})
            assert response.status_code == 201, response.text
            return response.json()

        def prescribe(self, patient_id):
            medicine = self.get(f"/inventory/medicines?pharmacy_id={pid}").json()[0]
            response = self.post("/prescriptions/", {"pharmacy_id": pid, "patient_id": patient_id,
                                                     "items": [{"medicine_id": medicine["id"], "quantity": 1}]})
            assert response.status_code == 201, response.text
            return response.json()

        def search(self, text):
            return [p["id"] for p in self.get(f"/patients/?pharmacy_id={pid}&search={text}").json()]

    return Ctx()


def test_create_and_read_back(ctx):
    created = ctx.patient(AYESHA)
    read = ctx.get(f"/patients/{created['id']}").json()
    for key, value in AYESHA.items():
        assert read[key] == value
    assert len(read["public_id"]) == 36
    assert read["deleted"] is False and read["prescription_count"] == 0


def test_search_by_last_name_phone_and_full_name(ctx):
    ayesha, bilal = ctx.patient(AYESHA), ctx.patient(BILAL)
    assert ctx.search("Synthetica") == [ayesha["id"]]
    assert ctx.search("5550202") == [bilal["id"]]
    assert ctx.search("Ayesha%20Synthetica") == [ayesha["id"]]
    assert ctx.search("first") == [] and ctx.search("zzz-no-such-patient") == []


def test_repeat_visitor_only_after_a_prescription(ctx):
    new = ctx.patient(BILAL)
    assert new["is_repeat_visitor"] is False
    listed = {p["id"]: p for p in ctx.get(f"/patients/?pharmacy_id={ctx.pharmacy_id}").json()}
    assert listed[new["id"]]["is_repeat_visitor"] is False and listed[new["id"]]["last_visit"] is None

    ctx.prescribe(new["id"])
    detail = ctx.get(f"/patients/{new['id']}").json()
    assert detail["is_repeat_visitor"] is True and detail["prescription_count"] == 1 and detail["last_visit"]
    listed = {p["id"]: p for p in ctx.get(f"/patients/?pharmacy_id={ctx.pharmacy_id}").json()}
    assert listed[new["id"]]["is_repeat_visitor"] is True


def test_removing_a_patient_keeps_prescriptions(ctx):
    patient = ctx.patient(AYESHA)
    rx = ctx.prescribe(patient["id"])

    assert ctx.delete(f"/patients/{patient['id']}").status_code == 204
    assert ctx.delete(f"/patients/{patient['id']}").status_code == 204, "removing twice is harmless"

    # Gone from lists and search, still readable by id, prescription untouched.
    assert patient["id"] not in ctx.search("")
    assert ctx.search("Synthetica") == []
    detail = ctx.get(f"/patients/{patient['id']}").json()
    assert detail["deleted"] is True and detail["deleted_at"] and detail["prescription_count"] == 1
    kept = ctx.get(f"/prescriptions/{rx['id']}").json()
    assert kept["patient_name"] == "Ayesha Synthetica" and len(kept["items"]) == 1
    history = ctx.get(f"/prescriptions/?pharmacy_id={ctx.pharmacy_id}&patient_id={patient['id']}").json()
    assert [r["id"] for r in history] == [rx["id"]]

    # The row is a tombstone, not a physical delete.
    assert ctx.sql("SELECT deleted_at IS NOT NULL, version FROM patients WHERE id = ?", patient["id"]) == [(1, 2)]
    assert ctx.sql("SELECT COUNT(*) FROM prescriptions WHERE patient_id = ?", patient["id"]) == [(1,)]

    # A removed patient cannot be edited or given new prescriptions or bills.
    assert ctx.put(f"/patients/{patient['id']}", {"notes": "x"}).status_code == 409
    medicine = ctx.get(f"/inventory/medicines?pharmacy_id={ctx.pharmacy_id}").json()[0]
    assert ctx.post("/prescriptions/", {"pharmacy_id": ctx.pharmacy_id, "patient_id": patient["id"],
                                        "items": [{"medicine_id": medicine["id"], "quantity": 1}]}).status_code in (400, 404)
    assert ctx.post("/billing/sales", {"pharmacy_id": ctx.pharmacy_id, "patient_id": patient["id"],
                                       "items": [{"medicine_id": medicine["id"], "quantity": 1}]}).status_code == 404


def test_patient_without_history_is_also_a_tombstone(ctx):
    patient = ctx.patient(BILAL)
    assert ctx.delete(f"/patients/{patient['id']}").status_code == 204
    assert ctx.sql("SELECT COUNT(*), MAX(deleted_at IS NOT NULL) FROM patients WHERE id = ?", patient["id"]) == [(1, 1)]


def test_queries_stay_inside_the_signed_in_pharmacy(ctx):
    mine = ctx.patient(AYESHA)
    other = ctx.post("/pharmacies/", {"name": "Other Synthetic Pharmacy"}).json()
    ctx.sql("INSERT INTO patients (public_id, pharmacy_id, first_name, last_name, phone, version) "
            "VALUES ('00000000-0000-4000-8000-0000000000b1', ?, 'Other', 'Synthetica', '0300-5559999', 1)",
            other["id"], write=True)
    theirs = ctx.sql("SELECT id FROM patients WHERE pharmacy_id = ?", other["id"])[0][0]

    assert ctx.search("Synthetica") == [mine["id"]], "pharmacy B's patient must not appear"
    assert ctx.get(f"/patients/?pharmacy_id={other['id']}").status_code == 403
    assert ctx.get(f"/patients/{theirs}").status_code == 404
    assert ctx.put(f"/patients/{theirs}", {"notes": "x"}).status_code == 404
    assert ctx.delete(f"/patients/{theirs}").status_code == 404
    assert ctx.post("/patients/", {"pharmacy_id": other["id"], **BILAL}).status_code == 403
    assert ctx.sql("SELECT COUNT(*) FROM patients WHERE pharmacy_id = ?", other["id"]) == [(1,)]
    assert ctx.sql("SELECT deleted_at FROM patients WHERE id = ?", theirs) == [(None,)]


def test_patient_details_stay_out_of_logs_and_audit(ctx, caplog):
    caplog.set_level(logging.DEBUG)
    patient = ctx.patient(AYESHA)
    ctx.put(f"/patients/{patient['id']}", {"address": "Synthetic street 9"})
    ctx.search("Synthetica")
    ctx.prescribe(patient["id"])
    ctx.delete(f"/patients/{patient['id']}")
    ctx.post("/patients/", {"pharmacy_id": 999, **BILAL})  # rejected request
    secrets = [*AYESHA.values(), *BILAL.values(), "Synthetic street 9"]
    # Skip the test client's own request log (httpx2 logs the URL it sends); in the app,
    # requests come from Electron and the server access log drops query strings.
    server_log = "\n".join(r.getMessage() for r in caplog.records if not r.name.startswith("httpx"))
    assert not [s for s in secrets if s in server_log]
    audit = " ".join(str(v) for row in ctx.sql("SELECT * FROM audit_logs") for v in row)
    assert not [s for s in secrets if s in audit]
    assert {"patient.created", "patient.updated", "patient.deleted"} <= {a for (a,) in ctx.sql("SELECT action FROM audit_logs")}
