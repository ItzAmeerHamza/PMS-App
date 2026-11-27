"""POST /api/v1/sync/push against real PostgreSQL."""

import threading
import uuid

import pytest

from .conftest import Events, load_fixture, push, sql


def test_valid_product_movement_patient_and_prescription_events_apply(client, make_shop, db_engine):
    shop = make_shop()
    ev = Events(shop["shop_id"])
    product, batch, patient, rx = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    events = [
        ev.product(product, sku="SYN-1", name="Synthamol"),
        ev.movement(product, 20, 20, batch_id=batch),
        ev.patient(patient, first_name="Ayla", allergies="Synthetic"),
        ev.prescription(patient, [{"product": product, "quantity": 3}], public_id=rx),
    ]
    results, _ = push(client, shop, events)
    assert results == ["applied"] * 4
    assert sql(db_engine, "SELECT sku, version FROM products WHERE public_id = :p", p=product) == [("SYN-1", 1)]
    assert sql(db_engine, "SELECT quantity FROM stock_batches WHERE public_id = :b", b=batch) == [(20,)]
    assert sql(db_engine, "SELECT first_name FROM patients WHERE public_id = :p", p=patient) == [("Ayla",)]
    assert sql(db_engine, "SELECT p.status, COUNT(i.id) FROM prescriptions p JOIN prescription_items i ON i.prescription_id = p.id "
                          "WHERE p.public_id = :r GROUP BY p.status", r=rx) == [("recorded", 1)]
    assert sql(db_engine, "SELECT COUNT(*) FROM processed_sync_events") == [(4,)]
    state = sql(db_engine, "SELECT events_applied, last_applied_sequence, last_result FROM synchronization_state")
    assert state == [(4, 4, "applied")]


def test_real_desktop_outbox_events_apply_and_replay_safely(client, make_shop, db_engine):
    fixture = load_fixture()
    shop = make_shop(shop_id=fixture["shop_id"])
    results, _ = push(client, shop, fixture["events"])
    assert results == ["applied"] * len(fixture["events"])
    for public_id, quantity in fixture["final_batch_quantities"].items():
        assert sql(db_engine, "SELECT quantity FROM stock_batches WHERE public_id = :b", b=public_id) == [(quantity,)]
    assert sql(db_engine, "SELECT COUNT(*) FROM stock_movements WHERE quantity_after != cloud_quantity_after") == [(0,)]
    assert sql(db_engine, "SELECT COUNT(*) FROM patients WHERE deleted_at IS NOT NULL") == [(1,)]
    assert sql(db_engine, "SELECT COUNT(*) FROM products WHERE deleted_at IS NOT NULL") == [(1,)]
    assert sql(db_engine, "SELECT status, version FROM prescriptions ORDER BY id") == [("recorded", 3), ("cancelled", 2)]

    # Lost acknowledgement: the shop sends the whole batch again.
    results, _ = push(client, shop, fixture["events"])
    assert results == ["already_processed"] * len(fixture["events"])
    for public_id, quantity in fixture["final_batch_quantities"].items():
        assert sql(db_engine, "SELECT quantity FROM stock_batches WHERE public_id = :b", b=public_id) == [(quantity,)]


def test_duplicate_event_id_does_not_double_apply_stock(client, make_shop, db_engine):
    shop = make_shop()
    ev = Events(shop["shop_id"])
    product, batch = uuid.uuid4(), uuid.uuid4()
    push(client, shop, [ev.product(product)])
    movement = ev.movement(product, 15, 15, batch_id=batch)
    assert push(client, shop, [movement])[0] == ["applied"]
    assert push(client, shop, [movement])[0] == ["already_processed"]
    assert push(client, shop, [movement, movement])[0] == ["already_processed", "already_processed"]
    assert sql(db_engine, "SELECT quantity FROM stock_batches WHERE public_id = :b", b=batch) == [(15,)]
    assert sql(db_engine, "SELECT COUNT(*) FROM stock_movements") == [(1,)]
    # The same movement under a new event id is a conflict, not a second delta.
    again = dict(movement, event_id=str(uuid.uuid4()), sequence=99)
    assert push(client, shop, [again])[0] == ["ordering_conflict"]
    assert sql(db_engine, "SELECT quantity FROM stock_batches WHERE public_id = :b", b=batch) == [(15,)]


def test_retried_patient_and_prescription_do_not_duplicate(client, make_shop, db_engine):
    shop = make_shop()
    ev = Events(shop["shop_id"])
    product, patient = uuid.uuid4(), uuid.uuid4()
    batch = [ev.product(product), ev.patient(patient), ev.prescription(patient, [{"product": product}])]
    push(client, shop, batch)
    push(client, shop, batch)
    assert sql(db_engine, "SELECT COUNT(*) FROM patients") == [(1,)]
    assert sql(db_engine, "SELECT COUNT(*) FROM prescriptions") == [(1,)]
    assert sql(db_engine, "SELECT COUNT(*) FROM prescription_items") == [(1,)]


def test_versions_must_follow_in_order(client, make_shop, db_engine):
    shop = make_shop()
    ev = Events(shop["shop_id"])
    patient = uuid.uuid4()
    push(client, shop, [ev.patient(patient, notes="v1")])
    v2 = ev.patient(patient, version=2, operation="updated", notes="v2")
    assert push(client, shop, [v2])[0] == ["applied"]
    stale = ev.patient(patient, version=2, operation="updated", notes="stale copy")
    gap = ev.patient(patient, version=5, operation="updated", notes="future")
    assert push(client, shop, [stale])[1][0] == {"event_id": stale["event_id"], "result": "ordering_conflict", "code": "stale_version"}
    assert push(client, shop, [gap])[1][0]["code"] == "version_gap"
    assert sql(db_engine, "SELECT version, notes FROM patients") == [(2, "v2")]
    assert push(client, shop, [ev.tombstone("patient", patient, 3)])[0] == ["applied"]
    assert sql(db_engine, "SELECT version, deleted_at IS NOT NULL FROM patients") == [(3, True)]
    assert push(client, shop, [ev.patient(patient, notes="created again")])[1][0]["code"] == "entity_exists"


def test_missing_patient_or_product_is_not_applied(client, make_shop, db_engine):
    shop = make_shop()
    ev = Events(shop["shop_id"])
    product = uuid.uuid4()
    push(client, shop, [ev.product(product)])
    orphan_rx = ev.prescription(uuid.uuid4(), [{"product": product}])
    assert push(client, shop, [orphan_rx])[1][0]["code"] == "missing_patient"
    patient = uuid.uuid4()
    push(client, shop, [ev.patient(patient)])
    unknown_product_rx = ev.prescription(patient, [{"product": product}, {"product": uuid.uuid4()}])
    assert push(client, shop, [unknown_product_rx])[1][0]["code"] == "missing_product"
    assert push(client, shop, [ev.movement(uuid.uuid4(), 5, 5)])[1][0]["code"] == "missing_product"
    assert sql(db_engine, "SELECT COUNT(*) FROM prescriptions") == [(0,)]
    assert sql(db_engine, "SELECT COUNT(*) FROM prescription_items") == [(0,)]
    assert sql(db_engine, "SELECT COUNT(*) FROM stock_movements") == [(0,)]


def test_failure_mid_prescription_leaves_nothing_partial(client, make_shop, db_engine, monkeypatch):
    from app.sync import apply

    shop = make_shop()
    ev = Events(shop["shop_id"])
    product, patient = uuid.uuid4(), uuid.uuid4()
    push(client, shop, [ev.product(product), ev.patient(patient)])
    # Break item insertion after the prescription row has been flushed.
    monkeypatch.setattr(apply, "ITEM_FIELDS", apply.ITEM_FIELDS + ("no_such_field",))
    rx = ev.prescription(patient, [{"product": product}, {"product": product}])
    assert push(client, shop, [rx])[1][0] == {"event_id": rx["event_id"], "result": "retryable_error", "code": "internal_error"}
    assert sql(db_engine, "SELECT COUNT(*) FROM prescriptions") == [(0,)]
    assert sql(db_engine, "SELECT COUNT(*) FROM prescription_items") == [(0,)]
    assert sql(db_engine, "SELECT COUNT(*) FROM processed_sync_events WHERE event_id = :e", e=rx["event_id"]) == [(0,)]
    monkeypatch.undo()
    assert push(client, shop, [rx])[0] == ["applied"], "the same event applies once the fault is gone"


def test_batch_stops_at_first_conflict_but_not_at_invalid_events(client, make_shop, db_engine):
    shop = make_shop()
    ev = Events(shop["shop_id"])
    patient, product = uuid.uuid4(), uuid.uuid4()
    bad_schema = ev.patient(uuid.uuid4())
    bad_schema["schema_version"] = 2
    no_name = ev.patient(uuid.uuid4())
    del no_name["payload"]["first_name"]
    events = [
        bad_schema,                                    # invalid: does not block
        no_name,                                       # invalid: does not block
        ev.patient(patient),                           # applied
        ev.prescription(uuid.uuid4(), [{"product": product}]),  # conflict: missing patient -> blocks the rest
        ev.product(product),                           # not processed
    ]
    results, detail = push(client, shop, events)
    assert results == ["invalid_event", "invalid_event", "applied", "ordering_conflict", "retryable_error"]
    assert [d.get("code") for d in detail] == ["schema:schema_version", "payload:first_name", None, "missing_patient",
                                               "blocked_by_earlier_event"]
    assert sql(db_engine, "SELECT COUNT(*) FROM products") == [(0,)]


def test_out_of_order_batch_is_applied_in_sequence_order(client, make_shop, db_engine):
    shop = make_shop()
    ev = Events(shop["shop_id"])
    product, patient = uuid.uuid4(), uuid.uuid4()
    events = [ev.product(product), ev.patient(patient), ev.prescription(patient, [{"product": product}])]
    results, _ = push(client, shop, list(reversed(events)))
    assert results == ["applied", "applied", "applied"]


def test_payload_must_match_the_envelope(client, make_shop):
    shop = make_shop()
    ev = Events(shop["shop_id"])
    wrong_id = ev.patient()
    wrong_id["payload"]["public_id"] = str(uuid.uuid4())
    wrong_version = ev.patient()
    wrong_version["entity_version"] = 2
    wrong_name = ev.patient()
    wrong_name["payload"]["event"] = "product.created"
    zero_delta = ev.movement(uuid.uuid4(), 0, 0)
    not_a_dict = "garbage"
    _, detail = push(client, shop, [wrong_id, wrong_version, wrong_name, zero_delta, not_a_dict])
    assert [(d["result"], d.get("code")) for d in detail] == [
        ("invalid_event", "payload:public_id_mismatch"), ("invalid_event", "payload:version_mismatch"),
        ("invalid_event", "schema:payload.event"), ("invalid_event", "payload:quantity_delta"),
        ("invalid_event", "schema:event")]


def test_concurrent_pushes_of_the_same_event_apply_once(client, make_shop, db_engine):
    from app.sync.service import process_push

    shop = make_shop()
    ev = Events(shop["shop_id"])
    product, batch = uuid.uuid4(), uuid.uuid4()
    push(client, shop, [ev.product(product)])
    movement = ev.movement(product, 7, 7, batch_id=batch)
    barrier = threading.Barrier(2)
    outcomes = []

    def worker():
        barrier.wait()
        outcomes.append(process_push([movement], uuid.UUID(shop["shop_id"]), uuid.UUID(shop["device_id"]))[0]["result"])

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert sorted(outcomes) == ["already_processed", "applied"]
    assert sql(db_engine, "SELECT quantity FROM stock_batches WHERE public_id = :b", b=batch) == [(7,)]
    assert sql(db_engine, "SELECT COUNT(*) FROM processed_sync_events WHERE event_id = :e", e=movement["event_id"]) == [(1,)]


def test_reported_outbox_counts_are_stored_as_last_known(client, make_shop, owner_headers):
    shop = make_shop(name="Reporting Shop")
    push(client, shop, [], outbox={"pending": 12, "failed": 1})
    status = client.get("/api/v1/admin/sync-status", headers=owner_headers).json()["items"][0]
    assert (status["reported_pending"], status["reported_failed"]) == (12, 1) and status["reported_at"]


def test_push_logs_carry_no_patient_details(client, make_shop, caplog):
    import logging

    caplog.set_level(logging.DEBUG)
    shop = make_shop()
    ev = Events(shop["shop_id"])
    push(client, shop, [ev.patient(first_name="Secretname", phone="0399-1234567", allergies="Secret allergy")])
    server_log = "\n".join(r.getMessage() for r in caplog.records if not r.name.startswith("httpx"))
    assert "sync push shop=" in server_log
    assert not [s for s in ("Secretname", "0399-1234567", "Secret allergy") if s in server_log]


@pytest.mark.parametrize("count", [501])
def test_oversized_push_is_rejected(client, make_shop, count):
    shop = make_shop()
    response = client.post("/api/v1/sync/push", headers=shop["headers"], json={"events": [{}] * count})
    assert response.status_code == 413
