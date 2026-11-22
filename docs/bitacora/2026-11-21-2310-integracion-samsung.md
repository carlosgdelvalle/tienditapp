# 2026-11-21 · Integración de caja y acceso del dueño en Samsung

- **Integración.** El merge `ce0b261` reúne `f4817a7` (caja) y `0e47cbc` (alta y QR).
- **Preparación.** `-PABARPAY_DEVICE_TEST=true` genera Abarpay QA con identificador independiente. El perfil de depuración acepta HTTP en loopback para el túnel USB. [Guía de pruebas](../produccion/pruebas-samsung.md).
- **Evidencia.** 376 pruebas Python y 176 de Android aprobadas. APK QA ensamblado e instalado junto a `mx.abarpay.mobile.dev` en Samsung SM-A165M, Android 16. Android resuelve el callback al QA. El backend SIMULADO de caja registró una autorización offline y conserva cero ventas al preparar la prueba. PostgreSQL 16.16 aislado, con migraciones 001–003 y rol de servicio restringido comprobado.
- **Pendiente.** Identificar o configurar la aplicación Native de Auth0 y su API. Verificar el inicio real y el QR, y completar el recorrido de venta offline en el teléfono.
