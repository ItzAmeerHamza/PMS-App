"""List screens can ask for one page. Omitting page still returns the full list."""

from datetime import date, timedelta

from .conftest import auth


def _client(demo_client, manager):
    headers = auth(manager)
    pid = manager["_pharmacy_id"]

    def get(path):
        response = demo_client.get("/api/v1" + path, headers=headers)
        assert response.status_code == 200, response.text
        return response.json()

    def post(path, body):
        response = demo_client.post("/api/v1" + path, headers=headers, json=body)
        assert response.status_code == 201, response.text
        return response.json()

    return pid, get, post


def test_medicine_pages_match_the_full_search_and_low_stock_filter(demo_client, manager):
    pid, get, post = _client(demo_client, manager)
    expiry = (date.today() + timedelta(days=400)).isoformat()
    for name in ("PageMed A", "PageMed B", "PageMed C"):
        post("/inventory/medicines", {
            "pharmacy_id": pid, "sku": name.replace(" ", "-"), "name": name, "unit_price": "5.00",
            "reorder_level": 1,
            "initial_batch": {"batch_number": name, "expiry_date": expiry, "quantity": 10},
        })
    for name in ("PageLow A", "PageLow B", "PageLow C"):
        post("/inventory/medicines", {
            "pharmacy_id": pid, "sku": name.replace(" ", "-"), "name": name, "unit_price": "5.00",
            "reorder_level": 50,
            "initial_batch": {"batch_number": name, "expiry_date": expiry, "quantity": 1},
        })

    full = get(f"/inventory/medicines?pharmacy_id={pid}&search=PageMed")
    assert [row["name"] for row in full] == ["PageMed A", "PageMed B", "PageMed C"]
    first = get(f"/inventory/medicines?pharmacy_id={pid}&search=PageMed&page=1&page_size=2")
    second = get(f"/inventory/medicines?pharmacy_id={pid}&search=PageMed&page=2&page_size=2")
    assert first["total"] == 3 and first["page"] == 1 and first["page_size"] == 2
    assert [row["name"] for row in first["items"]] == ["PageMed A", "PageMed B"]
    assert [row["name"] for row in second["items"]] == ["PageMed C"]

    low = get(f"/inventory/medicines?pharmacy_id={pid}&search=PageLow&low_stock=true&page=1&page_size=2")
    assert low["total"] == 3
    assert [row["name"] for row in low["items"]] == ["PageLow A", "PageLow B"]
    assert demo_client.get(f"/api/v1/inventory/medicines?pharmacy_id={pid}&page=0", headers=auth(manager)).status_code == 422


def test_patient_and_prescription_pages_keep_order(demo_client, manager):
    pid, get, post = _client(demo_client, manager)
    medicine = get(f"/inventory/medicines?pharmacy_id={pid}")[0]
    patients = []
    for last_name in ("PageA", "PageB", "PageC"):
        patients.append(post("/patients/", {
            "pharmacy_id": pid, "first_name": "Synthetic", "last_name": last_name, "phone": f"0300-{last_name}",
        }))
    for _ in range(3):
        post("/prescriptions/", {
            "pharmacy_id": pid, "patient_id": patients[0]["id"],
            "items": [{"medicine_id": medicine["id"], "quantity": 1}],
        })

    full_patients = get(f"/patients/?pharmacy_id={pid}&search=Synthetic%20Page")
    assert [row["last_name"] for row in full_patients] == ["PageA", "PageB", "PageC"]
    page = get(f"/patients/?pharmacy_id={pid}&search=Synthetic%20Page&page=1&page_size=2")
    assert page["total"] == 3
    assert [row["last_name"] for row in page["items"]] == ["PageA", "PageB"]

    full_rx = get(f"/prescriptions/?pharmacy_id={pid}&patient_id={patients[0]['id']}")
    assert len(full_rx) == 3
    first = get(f"/prescriptions/?pharmacy_id={pid}&patient_id={patients[0]['id']}&page=1&page_size=2")
    assert first["total"] == 3
    assert [row["id"] for row in first["items"]] == [row["id"] for row in full_rx[:2]]
    rest = get(f"/prescriptions/?pharmacy_id={pid}&patient_id={patients[0]['id']}&page=2&page_size=2")
    assert [row["id"] for row in rest["items"]] == [full_rx[2]["id"]]


def test_bill_page_keeps_the_period_summary(demo_client, manager):
    pid, get, post = _client(demo_client, manager)
    medicine = get(f"/inventory/medicines?pharmacy_id={pid}")[0]
    for _ in range(3):
        post("/billing/sales", {
            "pharmacy_id": pid,
            "customer_name": "Page Buyer",
            "items": [{"medicine_id": medicine["id"], "quantity": 1}],
        })
    full = get(f"/billing/sales?pharmacy_id={pid}&search=Page%20Buyer")
    assert len(full["sales"]) == 3 and full["summary"]["count"] == 3
    page = get(f"/billing/sales?pharmacy_id={pid}&search=Page%20Buyer&page=1&page_size=2")
    assert page["total"] == 3 and len(page["sales"]) == 2
    assert page["summary"]["count"] == 3
    assert [row["id"] for row in page["sales"]] == [row["id"] for row in full["sales"][:2]]
