# 2026-11-21 20:02 · tenencia · runtime producción PostgreSQL (corte vertical 1)

- PR / commits: rama cdv/integra-tenencia · server/runtime.py, server/tests/test_runtime_pg.py
- Qué cambió: Fábrica server.runtime.create_production_app con arranque fail-closed, identidad OIDC verificada y alta durable /api/signup. Entry documentado: uvicorn server.runtime:create_production_app --factory. La demo SQLite (server/main.py) queda intacta.
- Por qué: Primer corte vertical de tenencia/identidad. Las migraciones PG se aplican como paso separado (migrador/CI); el arranque solo verifica y falla cerrado.
- Evidencia:

      python -m pytest -q server/tests/test_runtime_pg.py   # 8 passed (~2s)
      python -m pytest -q server/tests                       # 299 passed, 20 skipped

- Riesgos abiertos: sin rutas de negocio ni cuentas bancarias sobre PG; wiring real de Android/navegador pendiente. GET /api/tenant/members e invitaciones sobre PG requieren cablear actor_context en la capa de servicio.
- Siguiente: rutas de negocio sobre PG y miembros/invitaciones; QR y primera venta quedan en el agente de dinero.
