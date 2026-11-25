# 2026-11-25 05:06 · Landing · Vista previa de La Libreta Clara

- **Qué cambió:** La portada prioriza efectivo, CoDi sin comisión por transacción y fiado. El cierre simulado muestra el efectivo recibido, el CoDi confirmado y el fiado pendiente con sus desgloses. La cuenta receptora de la tienda se explica junto al cobro en equipo.
- **Por qué:** Carlos eligió La Libreta Clara y pidió concentrar la portada en los cobros del mostrador. Inventario queda más abajo.
- **Evidencia:** Cinco pruebas de `server/tests/test_console.py` en verde. Se verificaron las rutas de la portada y sus destinos por HTTP, y el diseño en Chromium de 320 a 1135 px. El desglose se puede abrir con el teclado. Vista previa local con SQLite aislado y sin pey configurado.
- **Pendiente:** Validar en el piloto el cobro CoDi de dos personas autorizadas a la misma cuenta receptora antes de anunciarlo como disponible.
