# 2026-11-21 · Caja y operación sin conexión

- **Base:** `355db73`.
- **Qué cambió.** Se agregaron pruebas de aceptación para la conciliación CoDi con inventario agotado, el precio de una venta sin conexión, el reenvío tras perder una respuesta y la venta de la última unidad desde dos cajas. Se actualizaron los pasos de validación física y de accesibilidad en AstraTODO.
- **Evidencia en la base.** Cinco fallas reproducidas y seis pruebas existentes aprobadas. Los dos caminos CoDi devolvieron 500, la venta sin conexión se recalculó a 1900 centavos con un precio emitido de 1800, el reenvío obtuvo otro identificador de venta y la segunda venta de la última unidad fue rechazada.
- **Siguiente.** Verificar el candidato de caja con los mismos casos. Registrar por separado el resultado físico y la actualización del APK con operaciones pendientes.
