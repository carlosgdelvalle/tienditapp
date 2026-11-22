# 2026-11-22 · Dueño · Inventario, fiado, gastos y equipo

- **Cambio:** la consola QR permite ajustar existencias con motivo, ver movimientos, registrar cargos y abonos manuales de fiado, registrar gastos y administrar permisos de personas vinculadas. Caja muestra la existencia del catálogo PostgreSQL.
- **Evidencia física:** Chrome ajustó de 2 a 6. El Samsung SM-A165M mostró 6 y vendió una unidad por MXN 21.00 en efectivo SIMULADO. La consola y el Samsung mostraron 5. PostgreSQL registró un ajuste de +4 y el movimiento de la venta. Un segundo dueño vio inventario y movimientos vacíos. El ajuste directo de ese producto devolvió 404 y el catálogo móvil ajeno devolvió 403.
- **Verificación en Chrome:** cargo de MXN 80.00 y abono de MXN 30.00 dejaron MXN 50.00 por cobrar. Se registró un gasto de MXN 25.50. Se comprobaron cambios de permisos, suspensión y reactivación de una colaboradora vinculada. La prueba de PostgreSQL comprobó repetición de operaciones, rechazo de conteo obsoleto y aislamiento de cada sección.
- **Revisión:** DeepSeek Flash reprodujo la prueba PostgreSQL focalizada e identificó el editor obsoleto tras un conflicto. Chrome confirmó que la recarga cierra el editor y conserva la existencia más reciente. El alta de nuevos empleados queda pendiente del enrolamiento de personal.
- **Pruebas:** 329 del servidor, 16 de la app de referencia y 175 de Android aprobadas. Se ensambló la versión release.
- **Guía:** [Pruebas en Samsung](../produccion/pruebas-samsung.md).
