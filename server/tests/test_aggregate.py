"""M7 aggregate-data partner (SIMULADO): suppression, ledger, withdrawal.

Deterministic reproduction of one suppressed report (dominance and
inference-by-differencing) and one eligible delivery, plus withdrawal between
preparation and delivery and the HTTP route flow.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.aggregate import (
    AggregateService,
    ConsentLedger,
    Simulator,
    evaluate_cell,
)
from server.routes_aggregate import register as register_aggregate_routes

PURPOSE = "abastecimiento_agregado"
SCOPE = "zona-norte"
METRIC = "item_days"
RECIPIENT = "socio-distribuidor"


def store_ids(n: int) -> list[str]:
    return [f"s{i:02d}" for i in range(1, n + 1)]


def cohort(stores: list[str], value: int = 100) -> dict:
    return {store: {(METRIC, SCOPE): value} for store in stores}


def make_service(
    contributions: dict, *, consented: list[str] | None = None, max_ratio: float = 0.70
) -> AggregateService:
    service = AggregateService(
        consent=ConsentLedger(),
        simulator=Simulator(contributions),
        max_contribution_ratio=max_ratio,
    )
    for store in (consented if consented is not None else list(contributions)):
        service.opt_in(store, PURPOSE, SCOPE)
    return service


def make_client(service: AggregateService) -> TestClient:
    app = FastAPI()
    register_aggregate_routes(app, service=service)
    return TestClient(app)


# ---------------------------------------------------------------------------
# Suppression - dominance (70%)
# ---------------------------------------------------------------------------


def test_dominance_suppression_reproducible():
    # 11 stores; the top store holds 71% of the cell (above the 70% limit).
    ids = store_ids(11)
    values = {s: 29 for s in ids}
    values[ids[0]] = 710  # 710 / (710 + 10*29) = 710 / 1000 = 71%
    decision = evaluate_cell(ids, values)
    assert decision.allowed is False
    assert "dominance" in decision.reasons
    assert decision.dominance_ratio == pytest.approx(0.71)
    # A suppressed report never exposes the protected value or derived ratio.
    service = make_service(cohort(ids, value=29))
    service.simulator._contributions[ids[0]] = {(METRIC, SCOPE): 710}
    record = service.prepare(PURPOSE, SCOPE, METRIC, RECIPIENT)
    assert record.status == "suppressed"
    assert record.total is None
    assert record.dominance_ratio is None


def test_dominance_boundaries_below_and_at_allowed():
    # Concentration just below (69%) and exactly at (70%) the limit is allowed.
    below = store_ids(11)
    below_values = {s: 31 for s in below}
    below_values[below[0]] = 690  # 690 / 1000 = 69%
    at = store_ids(11)
    at_values = {s: 30 for s in at}
    at_values[at[0]] = 700  # 700 / 1000 = 70%
    assert evaluate_cell(below, below_values).allowed is True
    assert evaluate_cell(at, at_values).allowed is True


# ---------------------------------------------------------------------------
# Suppression - inference by differencing
# ---------------------------------------------------------------------------


def test_differencing_suppression():
    ids = store_ids(11)
    # 10 stores consent first; the 11th joins only after the first delivery.
    service = make_service(cohort(ids), consented=ids[:10])

    first = service.prepare(PURPOSE, SCOPE, METRIC, RECIPIENT)
    assert first.status == "allowed"
    service.authorize(first.id, "operador-socio")
    assert service.deliver(first.id).status == "delivered"

    # An 11-store cell overlapping the delivered 10-store cell would isolate
    # the new store by subtraction.
    service.opt_in(ids[10], PURPOSE, SCOPE)
    second = service.prepare(PURPOSE, SCOPE, METRIC, RECIPIENT)
    assert second.status == "suppressed"
    assert "differencing" in second.suppression_reasons
    assert second.total is None


# ---------------------------------------------------------------------------
# Eligible delivery recorded in the ledger
# ---------------------------------------------------------------------------


def test_eligible_delivery_recorded():
    ids = store_ids(10)
    service = make_service(cohort(ids))
    record = service.prepare(PURPOSE, SCOPE, METRIC, RECIPIENT)
    assert record.status == "allowed"
    assert record.total == 1000  # 10 x 100
    assert record.artifact_fingerprint and record.artifact_fingerprint.startswith(
        "sha256:"
    )

    authorized = service.authorize(record.id, "operador-socio")
    assert authorized.status == "authorized"
    assert authorized.operator == "operador-socio"

    delivered = service.deliver(record.id)
    assert delivered.status == "delivered"
    assert delivered.delivered_at is not None
    assert delivered.expires_at is not None

    # The ledger records the delivery and feeds it into differencing detection.
    assert service.ledger.get(record.id).status == "delivered"
    assert any(r.status == "delivered" for r in service.ledger.all())
    assert service.ledger.delivered_participant_sets(METRIC, RECIPIENT) == [
        tuple(ids)
    ]


# ---------------------------------------------------------------------------
# Withdrawal between preparation and delivery
# ---------------------------------------------------------------------------


def test_withdrawal_between_preparation_and_delivery():
    ids = store_ids(10)
    service = make_service(cohort(ids))
    record = service.prepare(PURPOSE, SCOPE, METRIC, RECIPIENT)
    service.authorize(record.id, "operador-socio")

    withdrawn = service.withdraw(ids[0], PURPOSE, SCOPE)
    assert withdrawn is not None and withdrawn.status == "withdrawn"

    delivered = service.deliver(record.id)
    assert delivered.status == "invalidated"
    assert delivered.invalidated_reason == "consent_withdrawn"

    # A withdrawn store stops contributing to any fresh preparation.
    assert ids[0] not in service.eligible_stores(PURPOSE, SCOPE)


# ---------------------------------------------------------------------------
# Reproducibility
# ---------------------------------------------------------------------------


def test_artifact_fingerprint_reproducible():
    ids = store_ids(10)
    first = make_service(cohort(ids)).prepare(PURPOSE, SCOPE, METRIC, RECIPIENT)
    second = make_service(cohort(ids)).prepare(PURPOSE, SCOPE, METRIC, RECIPIENT)
    assert first.status == second.status == "allowed"
    assert first.artifact_fingerprint == second.artifact_fingerprint


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


def test_aggregate_routes_end_to_end():
    ids = store_ids(10)
    service = make_service(cohort(ids))
    client = make_client(service)
    headers = {"X-Platform-Role": "operator"}

    meta = client.get("/api/aggregate/meta")
    assert meta.status_code == 200
    assert meta.json()["simulado"] is True
    assert meta.json()["minParticipants"] == 10

    prepared = client.post(
        "/api/aggregate/reports/prepare",
        headers=headers,
        json={
            "purpose": PURPOSE,
            "scope": SCOPE,
            "metric": METRIC,
            "recipient": RECIPIENT,
        },
    )
    assert prepared.status_code == 200
    record = prepared.json()
    assert record["status"] == "allowed"
    assert record["total"] == 1000
    report_id = record["id"]

    authorized = client.post(
        f"/api/aggregate/reports/{report_id}/authorize",
        headers=headers,
        json={"operator": "operador-socio"},
    )
    assert authorized.status_code == 200
    assert authorized.json()["status"] == "authorized"

    delivered = client.post(
        f"/api/aggregate/reports/{report_id}/deliver", headers=headers
    )
    assert delivered.status_code == 200
    assert delivered.json()["status"] == "delivered"

    ledger = client.get("/api/aggregate/ledger", headers=headers)
    assert ledger.status_code == 200
    assert any(item["status"] == "delivered" for item in ledger.json()["items"])


def test_aggregate_routes_analyst_cannot_deliver():
    service = make_service(cohort(store_ids(10)))
    client = make_client(service)
    operator = {"X-Platform-Role": "operator"}
    analyst = {"X-Platform-Role": "analyst"}

    prepared = client.post(
        "/api/aggregate/reports/prepare",
        headers=operator,
        json={
            "purpose": PURPOSE,
            "scope": SCOPE,
            "metric": METRIC,
            "recipient": RECIPIENT,
        },
    ).json()
    client.post(
        f"/api/aggregate/reports/{prepared['id']}/authorize",
        headers=operator,
        json={"operator": "operador-socio"},
    )

    denied = client.post(
        f"/api/aggregate/reports/{prepared['id']}/deliver", headers=analyst
    )
    assert denied.status_code == 403
    assert denied.json()["detail"]["code"] == "insufficient_access"


def test_aggregate_routes_analyst_hides_per_store_detail():
    service = make_service(cohort(store_ids(10)))
    client = make_client(service)
    operator = {"X-Platform-Role": "operator"}
    analyst = {"X-Platform-Role": "analyst"}

    prepared = client.post(
        "/api/aggregate/reports/prepare",
        headers=operator,
        json={
            "purpose": PURPOSE,
            "scope": SCOPE,
            "metric": METRIC,
            "recipient": RECIPIENT,
        },
    ).json()
    report_id = prepared["id"]

    operator_view = client.get(
        f"/api/aggregate/reports/{report_id}", headers=operator
    ).json()
    analyst_view = client.get(
        f"/api/aggregate/reports/{report_id}", headers=analyst
    ).json()

    assert "participants" in operator_view
    assert "participants" not in analyst_view
    assert operator_view["participantCount"] == analyst_view["participantCount"] == 10
