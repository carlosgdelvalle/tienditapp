# 2026-11-22 13:20 · consola · acceso del equipo Abarpay y cambio de tienda

- Rama / commits: `cdv/ergonomia-caja-android` · `server/platform_auth.py`, `server/routes_platform.py`, `server/static/platform.html`, `server/static/owner-console.html`, `server/static/console.html`.
- Qué cambió: `/platform` deja de usar el selector `X-Platform-Role` y exige una cuenta del equipo. El alta inicial sale de `ABARPAY_PLATFORM_ADMIN_EMAIL` y `ABARPAY_PLATFORM_ADMIN_PASSWORD`, la primera sesión obliga a cambiar la contraseña y el propietario invita al resto con un enlace de un solo uso. Cada cuenta tiene un rol (propietario, administrador, operaciones, crecimiento, ingresos o datos) que el servidor aplica en cada sección. La consola de tienda muestra un selector cuando la cuenta tiene más de una membresía y cambia de tienda con `POST /api/session/store`.
- Por qué: la consola desplegada seguía siendo la demo SQLite de una sola tienda, con PIN compartido, y la consola de plataforma mostraba un rol simulado sin autenticación. Carlos preguntó dónde estaban la tenencia múltiple y el acceso del equipo.
- Evidencia:

      .venv/bin/python -m pytest -q server/tests/test_platform_auth.py   # 6 passed
      .venv/bin/python -m pytest -q server/tests                        # 322 passed, 20 skipped
      curl /api/platform/auth/me                                        # authenticated=false, configured=true
      curl POST /api/platform/auth/login                                # 200 + cookie HttpOnly
      curl GET /api/platform/ingresos                                   # 200 con la sesión
      navegador local: alta, modal de contraseña, secciones y Equipo    # verificado a 1280 px

- Riesgos abiertos: el servicio `abarpay-api` sigue ejecutando `server.main:app` sobre SQLite, así que su `/console` es la demo de una tienda. La consola multiinquilino (`server/static/owner-console.html`) se sirve desde el runtime PostgreSQL, que todavía no está desplegado. Falta provisionar PostgreSQL y definir la identidad del dueño (LabsMobile o emisor SIMULADO de QA) para publicarla.
- Siguiente: configurar las variables de plataforma en Render, desplegar este cambio y verificar el acceso real del equipo. Después, decidir el plan de PostgreSQL para llevar la tenencia múltiple a producción.
