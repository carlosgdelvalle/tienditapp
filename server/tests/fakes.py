"""SIMULADO: in-memory PEY double for tests. It never performs network I/O."""

from __future__ import annotations

from typing import Any

from server.pey import PeyError, PeyTimeout


class FakePey:
    """SIMULADO - deterministic PEY client used only by the test suite."""

    simulated = True

    def __init__(self) -> None:
        self.qrs: dict[str, dict[str, Any]] = {}
        self.transactions: dict[str, list[dict[str, Any]]] = {}
        self.counter = 0
        self.create_timeout = False
        self.create_error: Exception | None = None
        self.reconcile_timeout = False
        self.create_image = "data:image/png;base64,U0lNVUxBRE8="

    def create_qr(
        self,
        amount_cents: int,
        concept: str,
        expiration_sec: int,
        sale_id: str,
    ) -> dict[str, Any]:
        if self.create_timeout:
            raise PeyTimeout("SIMULADO: timeout al crear QR")
        if self.create_error is not None:
            raise self.create_error
        self.counter += 1
        qr_id = "qr_sim_" + str(self.counter)
        self.qrs[qr_id] = {
            "amountCents": amount_cents,
            "concept": concept,
            "expirationSec": expiration_sec,
            "saleId": sale_id,
        }
        self.transactions.setdefault(qr_id, [])
        return {
            "id": qr_id,
            "image": self.create_image,
            "simulated": True,
        }

    def add_transaction(
        self,
        qr_id: str,
        transaction_id: str,
        amount_pesos: float | str,
        status: str = "completed",
    ) -> None:
        self.transactions.setdefault(qr_id, []).append(
            {
                "transactionId": transaction_id,
                "amount": amount_pesos,
                "status": status,
                "simulated": True,
            }
        )

    def qr_transactions(self, qr_id: str) -> list[dict[str, Any]]:
        if self.reconcile_timeout:
            raise PeyTimeout("SIMULADO: timeout al conciliar")
        return list(self.transactions.get(qr_id, []))

    def close(self) -> None:
        return None


def rejected_pey() -> FakePey:
    fake = FakePey()
    fake.create_error = PeyError("rejected", "SIMULADO: cobro rechazado")
    return fake
