"""Accept disconnected cash on the PostgreSQL path with two verified tills."""

import uuid
from concurrent.futures import ThreadPoolExecutor

import psycopg

from server.tests.test_employee_phone_pg import (
    _accept_invite,
    _create_invite,
    _enroll_phone,
    _owner_headers,
    _signup_owner,
    runtime,
)


def test_two_tills_keep_their_offline_receipts_and_flag_the_last_unit(runtime):
    owner = _signup_owner(runtime, store_name="Tienda de caja offline")
    other_owner = _signup_owner(runtime, store_name="Tienda ajena a caja offline")
    employee = _enroll_phone(runtime)
    invite = _create_invite(
        owner, employee.phone, can_sell=True, can_fiado=False, can_inventory=False,
    )
    assert _accept_invite(runtime.client, invite["token"], employee, name="Caja 2").status_code == 200
    product = owner.client.post(
        "/api/catalog",
        headers=_owner_headers(owner),
        json={"name": "Última pieza QA", "unit": "pieza", "priceCents": 2100, "stockMilli": 1000},
    )
    assert product.status_code == 200
    product_id = product.json()["id"]
    path = f"/api/owner/pos/{owner.tenant_id}"

    leases = []
    for actor in (owner.identity, employee):
        response = runtime.client.post(f"{path}/offline-lease", headers=actor.auth)
        assert response.status_code == 200
        lease = response.json()
        assert lease["expiresAt"] - lease["issuedAt"] == 43200
        assert any(item["id"] == product_id and item["priceCents"] == 2100 for item in lease["items"])
        leases.append(lease)
    assert leases[0]["leaseId"] != leases[1]["leaseId"]

    changed = owner.client.patch(
        f"/api/catalog/{product_id}", headers=_owner_headers(owner),
        json={"name": "Última pieza QA", "unit": "pieza", "priceCents": 2400},
    )
    assert changed.status_code == 200

    def sync(actor, key, body, target=path):
        return runtime.client.post(
            f"{target}/offline-sales", headers={**actor.auth, "Idempotency-Key": str(key)}, json=body,
        )

    events = [
        {
            "items": [{"productId": product_id, "qtyMilli": 1000}],
            "cashReceivedCents": 2500, "expectedTotalCents": 2100,
            "leaseId": lease["leaseId"], "occurredAt": lease["issuedAt"],
        }
        for lease in leases
    ]
    assert sync(employee, uuid.uuid4(), events[0]).status_code == 403
    other_path = f"/api/owner/pos/{other_owner.tenant_id}"
    assert sync(other_owner.identity, uuid.uuid4(), events[0], other_path).status_code == 403
    assert sync(owner.identity, uuid.uuid4(), {**events[0], "expectedTotalCents": 2400}).status_code == 409
    assert sync(owner.identity, uuid.uuid4(), {**events[0], "occurredAt": leases[0]["issuedAt"] - 1}).status_code == 409
    keys = [uuid.uuid4(), uuid.uuid4()]
    attempts = [(owner.identity, keys[0], events[0]), (employee, keys[1], events[1])]
    with ThreadPoolExecutor(max_workers=3) as workers:
        futures = [workers.submit(sync, *args) for args in [*attempts, attempts[0]]]
        results = [future.result(timeout=15) for future in futures]
    expected_ids = [str(uuid.uuid5(uuid.UUID(owner.tenant_id), str(key))) for key in keys]
    for result, folio in zip(results, [*expected_ids, expected_ids[0]], strict=True):
        assert result.status_code == 200, result.text
        sale = result.json()
        assert sale["saleId"] == folio
        assert (sale["totalCents"], sale["cashReceivedCents"], sale["changeCents"]) == (2100, 2500, 400)
        assert sale["items"][0]["unitPriceCents"] == 2100
    assert sync(owner.identity, keys[0], {**events[0], "cashReceivedCents": 2600}).status_code == 409

    with psycopg.connect(runtime.admin_dsn) as conn:
        assert conn.execute(
            "SELECT stock_milli FROM products WHERE id = %s", (product_id,),
        ).fetchone() == (-1000,)
        assert conn.execute(
            "SELECT reason, delta_milli FROM inventory_movements WHERE product_id = %s ORDER BY reason",
            (product_id,),
        ).fetchall() == [("sale", -1000), ("sale_oversell", -1000)]
        assert conn.execute(
            "SELECT count(*), sum(amount_cents) FROM payments WHERE tenant_id = %s",
            (owner.tenant_id,),
        ).fetchone() == (2, 4200)

    history = owner.client.get("/api/sales").json()["items"]
    assert {sale["saleId"] for sale in history} == set(expected_ids)
    assert other_owner.client.get("/api/sales").json()["items"] == []
