"""M7 aggregate-data partner (SIMULADO).

Opt-in and withdrawal consent, a deterministic SIMULADO simulator, controlled
publication with dominance and inference-by-differencing suppression, and a
delivery ledger that records each report as allowed, authorized, and finally a
recorded delivery.

Everything here is SIMULADO: no real store data and no network I/O. The whole
pipeline is deterministic given its inputs, so an independent reviewer can
reproduce one suppressed report and one eligible report from the same fixture
by calling the pure :func:`evaluate_cell` with the same participants and
values, or by rebuilding an :class:`AggregateService` with the same
:class:`Simulator` and :class:`ConsentLedger`.

Suppression rules (initial controls; review against the real report):
  * insufficient_participants - fewer than MIN_PARTICIPANTS stores per cell.
  * dominance - one store contributes more than MAX_CONTRIBUTION_RATIO.
  * differencing - combining this cell with a previously delivered cell
    (same metric and recipient) isolates one store by subtraction. This is
    the "complementary cell / auxiliary total" guard: two aggregates whose
    participant sets differ by exactly one store reveal that store's value.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import time as clock
from dataclasses import dataclass, replace
from typing import Any, Iterable

# ---------------------------------------------------------------------------
# Approved catalog and initial controls (docs/produccion/07, "Report cycle")
# ---------------------------------------------------------------------------

# The real report cycle requires at least 10 participants per cell and an
# individual contribution of no more than 25%. The four-reviewer rehearsal
# uses a 70% dominance example ("one contributing 70% of a zone"), so this
# module defaults to 70% and keeps both numbers configurable.
MIN_PARTICIPANTS = 10
MAX_CONTRIBUTION_RATIO = 0.70

# A delivered artifact expires for the limited-access recipient after 30 days.
DELIVERY_TTL_SECONDS = 30 * 24 * 60 * 60

# Approved catalog: dimensions and windows are restricted, never free-form.
APPROVED_PURPOSES = ("abastecimiento_agregado",)
APPROVED_SCOPES = ("zona-norte", "zona-centro")
APPROVED_METRICS = ("item_days", "stockouts", "ventas_cents")

RULES_VERSION = 1


# ---------------------------------------------------------------------------
# Consent
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Consent:
    """Versioned, revocable consent for one store, purpose, and scope."""

    store_id: str
    purpose: str
    scope: str
    version: int
    status: str  # "active" | "withdrawn"
    consented_at: float
    withdrawn_at: float | None = None


class ConsentLedger:
    """Versioned opt-in and withdrawal per store, purpose, and scope.

    Withdrawal never deletes history: it records a new version with status
    "withdrawn". A later opt-in re-activates with a higher version. A withdrawn
    store is excluded from every new contribution, while historical deliveries
    keep whatever the agreed treatment for prior data was.
    """

    def __init__(self) -> None:
        self._consents: dict[tuple[str, str, str], Consent] = {}

    @staticmethod
    def _key(store_id: str, purpose: str, scope: str) -> tuple[str, str, str]:
        return (store_id, purpose, scope)

    def opt_in(
        self, store_id: str, purpose: str, scope: str, now: float | None = None
    ) -> Consent:
        timestamp = clock.time() if now is None else now
        key = self._key(store_id, purpose, scope)
        existing = self._consents.get(key)
        consent = Consent(
            store_id=store_id,
            purpose=purpose,
            scope=scope,
            version=1 if existing is None else existing.version + 1,
            status="active",
            consented_at=timestamp,
        )
        self._consents[key] = consent
        return consent

    def withdraw(
        self, store_id: str, purpose: str, scope: str, now: float | None = None
    ) -> Consent | None:
        timestamp = clock.time() if now is None else now
        key = self._key(store_id, purpose, scope)
        existing = self._consents.get(key)
        if existing is None:
            return None
        consent = replace(
            existing,
            version=existing.version + 1,
            status="withdrawn",
            withdrawn_at=timestamp,
        )
        self._consents[key] = consent
        return consent

    def get(self, store_id: str, purpose: str, scope: str) -> Consent | None:
        return self._consents.get(self._key(store_id, purpose, scope))

    def is_active(self, store_id: str, purpose: str, scope: str) -> bool:
        consent = self._consents.get(self._key(store_id, purpose, scope))
        return consent is not None and consent.status == "active"

    def active_stores(self, purpose: str, scope: str) -> list[str]:
        return sorted(
            store_id
            for (store_id, p, s), consent in self._consents.items()
            if p == purpose and s == scope and consent.status == "active"
        )

    def all(self) -> list[Consent]:
        return list(self._consents.values())


# ---------------------------------------------------------------------------
# Simulator
# ---------------------------------------------------------------------------


class Simulator:
    """SIMULADO - deterministic store contributions per (metric, scope).

    The simulator stands in for the real aggregate data source (durable sales,
    stock, and payment events). It returns integer values in the metric's own
    unit (counts or MXN cents) and never performs I/O.
    """

    simulated = True

    def __init__(
        self, contributions: dict[str, dict[tuple[str, str], int]] | None = None
    ) -> None:
        self._contributions: dict[str, dict[tuple[str, str], int]] = (
            contributions or {}
        )

    def value(self, store_id: str, metric: str, scope: str) -> int:
        return self._contributions.get(store_id, {}).get((metric, scope), 0)

    def stores(self) -> list[str]:
        return sorted(self._contributions)

    @classmethod
    def sample(cls) -> "Simulator":
        """Deterministic SIMULADO cohort for the demo routes.

        zona-norte/item_days has 12 equal stores (an eligible cell when all
        consent). zona-centro/stockouts keeps the rehearsal's 70% dominance
        example on a small zone.
        """
        contributions: dict[str, dict[tuple[str, str], int]] = {}
        for i in range(1, 13):
            contributions[f"s{i:02d}"] = {("item_days", "zona-norte"): 100}
        contributions["c01"] = {("stockouts", "zona-centro"): 70}
        contributions["c02"] = {("stockouts", "zona-centro"): 15}
        contributions["c03"] = {("stockouts", "zona-centro"): 15}
        return cls(contributions)


# ---------------------------------------------------------------------------
# Suppression (pure, reviewer-reproducible)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CellDecision:
    """Pure suppression decision for one cell (reproducible by a reviewer)."""

    allowed: bool
    participants: tuple[str, ...]
    total: int
    dominance_ratio: float | None
    reasons: tuple[str, ...]  # machine codes
    details: tuple[str, ...]  # human-safe text (never reveals a protected value)


def evaluate_cell(
    participants: Iterable[str],
    values: dict[str, int],
    *,
    min_participants: int = MIN_PARTICIPANTS,
    max_contribution_ratio: float = MAX_CONTRIBUTION_RATIO,
    delivered_participant_sets: Iterable[Iterable[str]] = (),
) -> CellDecision:
    """Decide whether a cell may be published.

    Suppression triggers, in order:
      1. insufficient_participants - fewer than min_participants stores.
      2. dominance - a single store contributes more than max_contribution_ratio.
      3. differencing - combining this cell with a previously delivered cell
         (same metric and recipient) isolates one store by subtraction.
    """

    participants = tuple(sorted(participants))
    values = {store_id: int(values.get(store_id, 0)) for store_id in participants}
    total = sum(values.values())

    reasons: list[str] = []
    details: list[str] = []
    dominance: float | None = None

    if len(participants) < min_participants:
        reasons.append("insufficient_participants")
        details.append(
            f"Menos de {min_participants} participantes ({len(participants)})."
        )

    if total > 0:
        top = max(values.values())
        dominance = top / total
        if dominance > max_contribution_ratio:
            reasons.append("dominance")
            details.append(
                "Una tienda concentra más del "
                f"{max_contribution_ratio:.0%} del total."
            )

    new_set = set(participants)
    for delivered in delivered_participant_sets:
        if len(new_set ^ set(delivered)) == 1:
            reasons.append("differencing")
            details.append(
                "Combinar este corte con una entrega previa aislaría a una "
                "tienda por diferencia."
            )
            break

    return CellDecision(
        allowed=not reasons,
        participants=participants,
        total=total,
        dominance_ratio=dominance,
        reasons=tuple(reasons),
        details=tuple(details),
    )


# ---------------------------------------------------------------------------
# Delivery ledger
# ---------------------------------------------------------------------------


@dataclass
class DeliveryRecord:
    """One report through the publication gate.

    Lifecycle: suppressed | allowed -> authorized -> delivered, or invalidated.
    A suppressed record never reveals the protected value or derived ratio.
    """

    id: str
    purpose: str
    scope: str
    metric: str
    recipient: str
    status: str  # suppressed | allowed | authorized | delivered | invalidated
    participants: tuple[str, ...]
    total: int | None
    dominance_ratio: float | None
    suppression_reasons: tuple[str, ...] = ()
    suppression_details: tuple[str, ...] = ()
    operator: str | None = None
    artifact_fingerprint: str | None = None
    prepared_at: float = 0.0
    authorized_at: float | None = None
    delivered_at: float | None = None
    expires_at: float | None = None
    invalidated_reason: str | None = None


class DeliveryLedger:
    """Ledger of every prepared report, including suppressed and invalidated."""

    def __init__(self) -> None:
        self._records: dict[str, DeliveryRecord] = {}

    def add(self, record: DeliveryRecord) -> None:
        self._records[record.id] = record

    def get(self, record_id: str) -> DeliveryRecord | None:
        return self._records.get(record_id)

    def all(self) -> list[DeliveryRecord]:
        return list(self._records.values())

    def delivered_participant_sets(
        self, metric: str, recipient: str
    ) -> list[tuple[str, ...]]:
        """Participant sets already in the recipient's hands (differencing)."""
        return [
            record.participants
            for record in self._records.values()
            if record.status == "delivered"
            and record.metric == metric
            and record.recipient == recipient
        ]


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class AggregateError(Exception):
    pass


class RecordNotFoundError(AggregateError):
    pass


class InvalidStateError(AggregateError):
    pass


class AggregateService:
    """Consent + simulator + publication gate + delivery ledger in one place."""

    def __init__(
        self,
        consent: ConsentLedger | None = None,
        simulator: Simulator | None = None,
        *,
        min_participants: int = MIN_PARTICIPANTS,
        max_contribution_ratio: float = MAX_CONTRIBUTION_RATIO,
        now: Any = None,
    ) -> None:
        self.consent = consent or ConsentLedger()
        self.simulator = simulator or Simulator()
        self.ledger = DeliveryLedger()
        self.min_participants = min_participants
        self.max_contribution_ratio = max_contribution_ratio
        self._now = now or clock.time  # zero-arg callable returning seconds
        self.rules_version = RULES_VERSION

    # consent -----------------------------------------------------------

    def opt_in(self, store_id: str, purpose: str, scope: str) -> Consent:
        return self.consent.opt_in(store_id, purpose, scope, now=self._now())

    def withdraw(self, store_id: str, purpose: str, scope: str) -> Consent | None:
        return self.consent.withdraw(store_id, purpose, scope, now=self._now())

    def eligible_stores(self, purpose: str, scope: str) -> list[str]:
        return self.consent.active_stores(purpose, scope)

    # publication -------------------------------------------------------

    def prepare(
        self, purpose: str, scope: str, metric: str, recipient: str
    ) -> DeliveryRecord:
        """Compute a cell over currently-consented stores and gate it.

        The result is recorded in the ledger as either "suppressed" (with the
        permitted reasons, never the protected value) or "allowed" (with an
        artifact fingerprint for the reviewer to reproduce).
        """

        participants = self.eligible_stores(purpose, scope)
        values = {s: self.simulator.value(s, metric, scope) for s in participants}
        delivered = self.ledger.delivered_participant_sets(metric, recipient)
        decision = evaluate_cell(
            participants,
            values,
            min_participants=self.min_participants,
            max_contribution_ratio=self.max_contribution_ratio,
            delivered_participant_sets=delivered,
        )
        record = DeliveryRecord(
            id="rep_" + secrets.token_hex(6),
            purpose=purpose,
            scope=scope,
            metric=metric,
            recipient=recipient,
            status="allowed" if decision.allowed else "suppressed",
            participants=decision.participants,
            total=decision.total if decision.allowed else None,
            dominance_ratio=decision.dominance_ratio if decision.allowed else None,
            suppression_reasons=decision.reasons,
            suppression_details=decision.details,
            prepared_at=self._now(),
        )
        if decision.allowed:
            record.artifact_fingerprint = self._fingerprint(record)
        self.ledger.add(record)
        return record

    def authorize(
        self,
        record_id: str,
        operator: str,
        *,
        recipient: str | None = None,
    ) -> DeliveryRecord:
        """Privacy and business owners sign an allowed version.

        Changing the recipient after preparation invalidates the prior approval
        (docs 07: "Changing eligibility or recipient invalidates prior
        approval").
        """

        record = self._require(record_id)
        if record.status != "allowed":
            raise InvalidStateError(
                f"El reporte no está autorizable ({record.status})."
            )
        if recipient is not None and recipient != record.recipient:
            record.status = "invalidated"
            record.invalidated_reason = "recipient_changed"
            return record
        record.status = "authorized"
        record.operator = operator
        record.authorized_at = self._now()
        return record

    def deliver(self, record_id: str) -> DeliveryRecord:
        """Record a delivery, re-validating that consent still holds.

        A store that withdrew between preparation/authorization and delivery
        invalidates the report: its new contribution is excluded and the
        frozen participant set no longer matches current consent.
        """

        record = self._require(record_id)
        if record.status != "authorized":
            raise InvalidStateError(
                f"El reporte no está listo para entregarse ({record.status})."
            )
        withdrawn = [
            store_id
            for store_id in record.participants
            if not self.consent.is_active(store_id, record.purpose, record.scope)
        ]
        if withdrawn:
            record.status = "invalidated"
            record.invalidated_reason = "consent_withdrawn"
            return record
        record.status = "delivered"
        record.delivered_at = self._now()
        record.expires_at = record.delivered_at + DELIVERY_TTL_SECONDS
        return record

    # helpers -----------------------------------------------------------

    def _require(self, record_id: str) -> DeliveryRecord:
        record = self.ledger.get(record_id)
        if record is None:
            raise RecordNotFoundError(f"Reporte no encontrado: {record_id}")
        return record

    def _fingerprint(self, record: DeliveryRecord) -> str:
        """Version the data, rules, and artifact so a reviewer can reproduce."""
        payload = {
            "rules": self.rules_version,
            "purpose": record.purpose,
            "scope": record.scope,
            "metric": record.metric,
            "recipient": record.recipient,
            "participants": list(record.participants),
            "values": {
                store_id: self.simulator.value(
                    store_id, record.metric, record.scope
                )
                for store_id in record.participants
            },
        }
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        return "sha256:" + digest


def default_simulado_service() -> AggregateService:
    """Deterministic SIMULADO service for the demo routes.

    Mirrors the rehearsal ("8 of 20 invited stores accepted"): 12 of 20 invited
    stores consent to zona-norte/item_days, yielding an eligible cell; the
    zona-centro/stockouts zone keeps the 70% dominance example.
    """

    service = AggregateService(consent=ConsentLedger(), simulator=Simulator.sample())
    for store_id in service.simulator.stores():
        if store_id.startswith("s"):
            service.opt_in(store_id, "abastecimiento_agregado", "zona-norte")
        else:
            service.opt_in(store_id, "abastecimiento_agregado", "zona-centro")
    return service
