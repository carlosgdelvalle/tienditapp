# G1 — Integración: walkthrough de aceptación por API (evidencia)

- **Fecha:** 2026-11-21 (CDMX)
- **SHA verificado:** c266d8c528cebc611fb713ce0e15113797baf5d7 (HEAD, "feat(m6): añade métricas, suscripción piloto y reconciliación CoDi")
- **Entorno:** Python 3.12.16 (.venv), PostgreSQL 17 en 127.0.0.1:5432 (db abarpay_dev), rol de servicio abarpay_app (NOLOGIN, no superuser, no BYPASSRLS)
- **Suite completa:** python -m pytest server/tests -q → **311 passed** (10.99s)
- **Modo:** MODO_DEMO=true + **FakePey SIMULADO** (nunca llama a la API real de pey). Sin dinero real ni datos reales de terceros.
- **Boot:** create_app(settings=Settings(...modo_demo=True, seed_catalog=True...), pey_client=FakePey()) — el mismo create_app que arranca uvicorn server.main:app; aquí se inyecta FakePey (marcado SIMULADO) en lugar de PeyClient.

---

## Veredictos

| Escenario | Veredicto | Alcance verificado por API |
|---|---|---|
| **B1** Aislamiento entre dos tenants | ✅ **PASS** | Registro desde cero vía signup_tenant (SECURITY DEFINER), códigos idénticos, lecturas/escrituras cruzadas denegadas, sin revelación de existencia |
| **B2** QR y reemplazo de dispositivo | ✅ **PASS** | Registro de dispositivo, reto crear→aprobar→canje único, expiración (120s), código erróneo, revocación |
| **B3** Banca y dinero (FakePey SIMULADO) | ✅ **PASS** | QR con bankAccountId exacto, conciliación por webhook firmado + GET /transaction/codi/qr/{id}, duplicado absorbido, monto distinto → por_conciliar, fallo del proveedor |
| **B5** Cierre de caja y deuda (fiado) | ✅ **PASS** | Fondo inicial, venta, desviación de conteo, entrega aceptada; límite→override→abono parcial→liquidación→export sin PII |
| **B7** Negocio y privacidad | ✅ **PASS** | Fixture SIMULADO reconciliado (90% por monto CoDi), supresión por dominancia y por diferencia, una entrega elegible + una suprimida |
| **B4 / B6 / B8** | ⛔ **BLOQUEADO (gates externos)** | Requieren teléfono físico/ADB (B4, B6) y APK firmado (B8) — ver sección final |

**Nada FALLÓ.** Todos los pasos observados coincidieron con lo esperado.

---

## B1 · Registro, invitaciones y aislamiento — PASS

**Procedimiento:** aplicar migraciones migrations/001|002|003 (idempotentes) sobre abarpay_dev; registrar dos tenants desde cero con la ruta de producción signup_tenant (vía PostgresOnboardingStore.signup); sembrar en cada tenant un producto con el **mismo** código de barras 750000000001; operar con el rol de servicio abarpay_app + set_tenant_context (RLS).

**Esperado:** un tenant no lee/escribe filas del otro; sin cambios de saldo; sin revelación de existencia.

**Observado (transcrito):**

    [PASS] signup Tienda Aurora :: 0fceb365-...
    [PASS] signup Tienda Beta  :: bf588918-...
    [PASS] Aurora clean seed (0 products)
    [PASS] identical barcode 750000000001 in BOTH tenants
    [PASS] Aurora reads own products only :: ['Producto Aurora']
    [PASS] Aurora cannot read Beta product (0 rows) :: count=0
    [PASS] Beta cannot read Aurora product (0 rows) :: count=0
    [PASS] Aurora INSERT into Beta denied (InsufficientPrivilege)
    [PASS] Aurora product count unchanged (1)
    [PASS] No context -> 0 rows read
    [PASS] No context INSERT denied
    [PASS] Context reverts after COMMIT (1 -> 0) :: 1->0
    [PASS] Cross-tenant composite FK rejected (ForeignKeyViolation)
    [PASS] One-to-one store invariant (2nd store fails)
    RESULT B1: ALL PASS

**Evidencia de "sin revelación de existencia":** leer un id de producto de Tienda Beta desde Tienda Aurora devuelve **0 filas** (indistinguible de un id inexistente); la escritura cruzada falla con InsufficientPrivilege (política WITH CHECK) y el conteo de productos del tenant atacante queda intacto (1).

**Ruta de evidencia:** migrations/001_schema.sql (RLS + FORCE + política *_tenant_isolation + FKs compuestas), server/db_pg.py, server/onboarding.py (signup_tenant), server/tests/test_tenancy_pg.py. Nota: las rutas HTTP de negocio (catálogo/ventas) siguen en el camino SQLite mono-tenant del demo (docs/produccion/contracts/routes.md); el aislamiento de producción se verifica en el camino de datos PG/RLS, que es el que B1 evalúa.

---

## B2 · QR y reemplazo de dispositivo — PASS

**Procedimiento:** router auth_routes con MemoryIdentityStore (SIMULADO) y un TokenValidator con clave RSA local (sin red); identidad simulada por Authorization: Bearer. Flujo de reto por navegador + dispositivo.

**Esperado:** reto crear → aprobar → canje **una sola vez**; expiración; código erróneo rechazado; revocación de dispositivo.

**Observado (transcrito):**

    [PASS] device register -> 200
    [PASS] challenge create -> 6-digit code + abarpay:// QR :: code=343818
    [PASS] browser cookie set (HttpOnly, Path scoped)
    [PASS] approve (correct code+sig) -> approved :: 200
    [PASS] GET challenge -> approved
    [PASS] exchange -> session for t_A :: 200 owner-1@example.com
    [PASS] replay exchange -> 409 (one-time) :: 409 El reto aún no ha sido aprobado
    [PASS] expired challenge approve -> 409 'El reto expiró'
    [PASS] wrong code approve -> 403 'El código no coincide'
    [PASS] device revoke -> 200 {'ok':true}
    [PASS] device gone after revoke
    RESULT B2: ALL PASS

**Evidencia de canje único:** el segundo POST /api/auth/challenge/{id}/exchange con la misma cookie devuelve **409** (el reto ya fue consumido).

**Ruta de evidencia:** server/auth_routes.py, server/identity.py (approve_challenge / exchange_challenge / revoke_device), server/tests/test_auth.py; el mismo contrato persiste en PG en server/tests/test_identity_pg.py (test_challenge_transition_one_time, test_device_roundtrip_and_revoke). Gate externo: el OIDC real (Auth0/Entra) no está configurado en el entorno (usa token RSA local SIMULADO).

---

## B3 · Banca y dinero (FakePey SIMULADO) — PASS

**Procedimiento:** signup → cuenta bancaria (CLABE válida, queda PENDING con last4) → activar → venta PEY con header X-Tenant-Id → verificar bankAccountId en FakePey → conciliar → webhook firmado/duplicado/monto distinto → fallo de proveedor.

**Esperado:** destinatario exacto al crear QR (cuenta ACTIVE); conciliación del cargo previo; duplicados absorbidos; monto distinto nunca paga; fallo = incertidumbre (202) o rechazo (502).

**Observado (transcrito):**

    [PASS] signup -> 200 (tenant+store+owner)
    [PASS] PEY sale without active account -> 409 NO_ACTIVE_BANK_ACCOUNT
    [PASS] bank account create -> PENDING + last4 (full CLABE masked) :: codiStatus=PENDING last4=4150
    [PASS] activate -> ACTIVE
    [PASS] PEY sale -> 200 pending, demo charge 1c :: total=1800 charged=1
    [PASS] create_qr sent bankAccountId = ACTIVE account :: bankAccountId=ba_sim_1
    [PASS] create_qr amount = 1c (demo) :: amountCents=1
    [PASS] reconcile -> paid_pey (txId=tx_sim_1)
    [PASS] replacement account now routes charges (not the pending one) :: bankAccountId=ba_sim_3
    [PASS] signed webhook -> applied (paid_pey) :: outcome=applied
    [PASS] duplicate webhook -> outcome duplicate
    [PASS] amount mismatch -> outcome amount_mismatch :: status=por_conciliar
    [PASS] mismatch sale -> por_conciliar (never paid)
    [PASS] provider timeout -> 202 por_conciliar with saleId
    [PASS] provider rejection -> 502 failed with saleId
    RESULT B3: ALL PASS

**Evidencia de destinatario exacto:** FakePey.qrs[qr].bankAccountId coincide con la cuenta ACTIVA (no con la cuenta PENDING); al activar una cuenta de reemplazo, el cobro cambia explícitamente a esa cuenta. La CLABE completa nunca aparece en el payload (last4 + simulated:true).

**Ruta de evidencia:** server/pey.py (create_qr con bankAccountId), server/main.py (POST /api/sales → resolve_active_bank_account → 409 NO_ACTIVE_BANK_ACCOUNT), server/payments.py (apply_payment), server/tests/test_pey_flow.py. Gate externo: el pago real de $0.01 lo hace una persona (pey no tiene sandbox) — fuera de alcance de este walkthrough.

---

## B5 · Cierre de caja y deuda — PASS

**Procedimiento:** abrir caja con fondo, venta en efectivo, cierre con desviación de conteo, entrega aceptada por el dueño; luego fiado con límite, sobregiro denegado, override del dueño, abono parcial, liquidación y exportación CSV.

**Esperado:** desviación auditada (no corregida en silencio); entrega con observed; el sobregiro se rechaza salvo autorización del dueño; el ledger y la auditoría quedan registrados; la exportación no filtra PII.

**Observado (transcrito):**

    [PASS] till open (float 50000, emp 2)
    [PASS] cash sale (emp 2, product 1 = 1800c)
    [PASS] till close with variance (50800 vs 51800 -> -1000) :: expected=51800 variance=-1000
    [PASS] handover accepted by owner (observed) :: status=observed acceptReason=falta por aclarar
    [PASS] audit variance (product 2: 18000->17000, delta -1000)
    [PASS] charge 3000 (emp 2) -> balance 3000
    [PASS] charge beyond limit -> 409 CREDIT_LIMIT_EXCEEDED
    [PASS] employee cannot override (403)
    [PASS] owner override 3000 -> balance 6000 (audit reason kept)
    [PASS] partial repayment 1500 -> balance 4500, not settled
    [PASS] payoff 4500 -> balance 0, settled
    [PASS] overpayment -> 409 OVERPAYMENT
    [PASS] ledger audit history :: ['charge','charge','payment','payment']
    [PASS] employee cannot export (403)
    [PASS] owner export -> CSV
    [PASS] export has no PII (no phone) :: rows=4
    RESULT B5: ALL PASS

**Ruta de evidencia:** server/routes_till.py + server/till.py, server/routes_fiado.py + server/fiado.py, server/tests/test_checkout_till.py, server/tests/test_fiado_m4.py.

---

## B7 · Negocio y privacidad — PASS

**Procedimiento:** reconciliación CoDi del fixture SIMULADO (independiente), separación de acceso por rol, y pipeline de agregados (consentimiento → prepare → authorize → deliver) con supresión por dominancia, por diferencia y retiro entre preparación y entrega.

**Esperado:** 90% confirmado por **monto CoDi** (no por registrado); supresión sin exponer valor protegido ni ratio; una entrega elegible registrada + una suprimida.

**Observado (transcrito):**

    [PASS] reconcile fixture: 1.8M / 2.0M = 90% by CoDi amount :: basis=codiAmount
    [PASS] cross-comparison (recorded basis) rejected
    [PASS] GET /api/analytics/reconciliation (support) -> simulado 90%
    [PASS] analytics access separation: finance blocked from margin
    [PASS] analytics access separation: analytics blocked from reconciliation
    [PASS] aggregate meta -> simulado, min=10, max=0.70
    [PASS] eligible report prepared (12 stores, total=1200) :: status=allowed participantCount=12
    [PASS] authorize -> authorized
    [PASS] deliver -> delivered (eligible, recorded)
    [PASS] ledger records the delivered report
    [PASS] analyst hides per-store detail (no participants) :: op=12 an=12
    [PASS] dominance: evaluate_cell disallows 71% :: ratio=0.71
    [PASS] dominance: report suppressed, total & ratio hidden :: status=suppressed reasons=('dominance',)
    [PASS] differencing: 11th store joins after delivery -> suppressed :: reasons=('differencing',)
    [PASS] withdrawal between prep & delivery -> invalidated :: reason=consent_withdrawn
    [PASS] withdrawn store excluded from new preparation
    RESULT B7: ALL PASS

**Ruta de evidencia:** server/analytics.py (reconcile_codi, simulado_reconciliation, codis_confirmation_rate), server/routes_analytics.py, server/aggregate.py (evaluate_cell, AggregateService, Simulator), server/routes_aggregate.py, server/tests/test_analytics.py, server/tests/test_aggregate.py.

---

## Resumen final

- **PASS:** B1, B2, B3, B5, B7 — los cinco escenarios de aceptación por API del alcance G1 se reprodujeron contra el servidor integrado y cada paso coincidió con lo esperado.
- **FAIL:** ninguno.
- **BLOQUEADO (gates externos, no son defectos de código):**
  - **B4** (venta offline + recepción de mercancía): requiere Android físico con ADB, modo avión, reinicio y una segunda caja.
  - **B6** (ergonomía): requiere teléfono físico (modelo/versión sin número de serie), TalkBack, texto ampliado, luz alta e interrupción.
  - **B8** (release recuperable): requiere APK firmado (reinstalar/actualizar, restaurar base, rollback, verificar SHA por auto-CD).
  - **Además pendiente de operación humana/real:** pago CoDi real de $0.01 (B3/G2 — pey no tiene sandbox), OIDC real Auth0/Entra (B2 usa token RSA local SIMULADO), y decisión de dominio/CD para G2.
