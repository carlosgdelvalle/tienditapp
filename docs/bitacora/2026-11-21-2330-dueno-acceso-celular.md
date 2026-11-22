# 2026-11-21 23:30 · Dueño · Acceso desde el celular

- **Cambio:** el dueño vincula el celular con un código SMS, crea su tienda y abre la consola por QR. Para volver a entrar, la app usa la clave que guardó en Android Keystore.
- **Motivo:** el dueño administra su acceso en Abarpay con su número de celular. Se conserva la aprobación del QR desde la app. [Decisión 0006](../decisiones/0006-acceso-dueno-celular.md)
- **Evidencia:** recorrido con PostgreSQL 16, Chrome y Samsung SM-A165M con Android 16. El SMS fue SIMULADO. Al reiniciar, la app volvió a entrar sin SMS. El QR se escaneó con la cámara y se aprobó desde el Samsung. Otro navegador y el segundo canje fueron rechazados. La consola registró una sola venta de MXN 18.00 y mostró MXN 2.00 de cambio.
- **Verificación automatizada:** 328 pruebas del servidor, 16 de la app de referencia y 175 de Android. El APK QA se instaló y la compilación `assembleRelease` pasó.
- **Pendientes del piloto:** verificar entrega por operador autorizado e implementar recuperación y traslado de dispositivo. Validar desbloqueo local para comercios que comparten el teléfono.
