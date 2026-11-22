"""Employee mobile operations backed by the same audited ledgers.

A verified Abarpay phone bearer resolves its membership for the tenant in the
path. The live membership and the relevant permission flag are re-read on every
request, so a revocation or downgrade takes effect without a new token.
"""

from dataclasses import dataclass
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from .auth_routes import IdentityContext, require_identity
from .owner_operations_pg import (
    FiadoEntryCreate,
    StockAdjust,
    add_fiado_entry,
    adjust_stock,
    customer_detail,
    list_customers,
    list_inventory,
)
from .owner_phone import MobileIdentity

router = APIRouter(prefix="/api/employee")


@dataclass(frozen=True)
class EmployeeContext:
    tenant_id: str
    user_id: str


def _require_employee(permission: str):
    def dependency(
        tenant_id: UUID,
        request: Request,
        ctx: IdentityContext = Depends(require_identity),
    ) -> EmployeeContext:
        if not isinstance(ctx.token, MobileIdentity):
            raise HTTPException(403, "Entra desde tu celular vinculado.")
        service = request.app.state.identity_service
        membership = service.select_tenant(ctx.user.id, str(tenant_id))
        if membership.role != "employee" or not getattr(membership, permission):
            raise HTTPException(403, "No tienes permiso para esta acción.")
        return EmployeeContext(tenant_id=str(tenant_id), user_id=ctx.user.id)

    return dependency


@router.get("/{tenant_id}/inventory")
def employee_inventory(
    request: Request,
    actor: EmployeeContext = Depends(_require_employee("can_inventory")),
):
    return list_inventory(request, actor.tenant_id, actor.user_id)


@router.post("/{tenant_id}/inventory/{product_id}/adjust")
def employee_adjust_stock(
    product_id: UUID,
    request: Request,
    body: StockAdjust,
    key: UUID = Header(alias="Idempotency-Key"),
    actor: EmployeeContext = Depends(_require_employee("can_inventory")),
):
    return adjust_stock(request, actor.tenant_id, actor.user_id, product_id, body, key)


@router.get("/{tenant_id}/fiado/customers")
def employee_customers(
    request: Request,
    actor: EmployeeContext = Depends(_require_employee("can_fiado")),
):
    return list_customers(request, actor.tenant_id, actor.user_id)


@router.get("/{tenant_id}/fiado/customers/{customer_id}")
def employee_customer_detail(
    customer_id: UUID,
    request: Request,
    actor: EmployeeContext = Depends(_require_employee("can_fiado")),
):
    return customer_detail(request, actor.tenant_id, actor.user_id, customer_id)


@router.post("/{tenant_id}/fiado/customers/{customer_id}/entries")
def employee_add_fiado_entry(
    customer_id: UUID,
    request: Request,
    body: FiadoEntryCreate,
    key: UUID = Header(alias="Idempotency-Key"),
    actor: EmployeeContext = Depends(_require_employee("can_fiado")),
):
    return add_fiado_entry(request, actor.tenant_id, actor.user_id, customer_id, body, key)
