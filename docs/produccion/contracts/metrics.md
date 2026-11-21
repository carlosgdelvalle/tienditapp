# Metrics and gross-margin contract

- **Contract:** Durable event sources, weighted-average-cost snapshot, gross margin
- **Version:** 1.0
- **Owner:** D2 Contracts — Pro domain owner
- **Consumers:** M6 (Analytics and Control), I4 (Platform), M3 (Purchasing and replenishment — supplies cost), G3 (Commercial operations), G1 (Integration)
- **Fixture:** two test tenants — "Tienda Aurora" (tenant A) and "Tienda Beta" (tenant B) — one store each
- **Acceptance:** B5 · Till close and debt; B7 · Business and privacy

## Invariants

1. **Every metric derives from a durable event source.** Aggregates come from `sales`, `sale_items`, `payments`, `inventory_movements`, `fiado_entries`, purchase `receipts`, and `till_shifts` — never from transient client state or screen state.
2. **Weighted-average cost is snapshotted at sale time.** On each historical sales line the weighted-average cost in effect at the moment of sale is recorded in cents (same basis, quantity, and currency). M3 records purchase cost in cents and quantity received when a stock receipt is approved; a later purchase cannot change a closed margin.
3. **Gross merchandise margin = net sales minus attributable cost.** Computed on the same basis, quantity, and currency (integer cents), with discounts and returns documented and deducted.
4. **Never impute zero cost.** A line with unknown or missing cost is shown separately with its coverage reported; it is never treated as 100% margin and never given a synthetic zero.
5. **Unknown-cost and offline-conflict lines are segregated.** Reports show them separately and state coverage explicitly; they do not pollute the aggregate margin.
6. **Verified payment reconciliation applies to every aggregation.** A sale only counts as collected when `apply_payment` (or the production equivalent) marks it paid; pending/`por_conciliar`/`failed` never count as revenue.
7. **Tenant scoping.** Metrics are computed per tenant and never mix Tienda Aurora's events with Tienda Beta's.

## Acceptance scenarios

- **B5 · Till close and debt** — Two operators, an opening float, a sale, a count variance, and an accepted handover; credit beyond the limit, owner authorization, partial repayment, settlement, then export after returning to Gratis. Expected: audited variance, a reconciled ledger, and audit history that ties every figure back to a durable event.
- **B7 · Business and privacy** — Load the SIMULADO fixture and independently recalculate funnel and money; verify the gross-margin figure reconciles to sales lines and their snapshotted cost, and that suppressed/eligible reports behave as configured.

## Provenance

- Guide 09: "Dependency between purchasing and margin reports" (M3/M6) and scenario B5.
- Current demo note: the SQLite demo has no purchase cost (`docs/v2-contract.md` states inventory value = price × stock, "no hay costo"). Cost capture arrives with M3; this contract freezes the production rule so M3 and M6 agree before either is built.
