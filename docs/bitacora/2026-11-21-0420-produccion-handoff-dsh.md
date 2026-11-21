# 2026-11-21 · Handoff de producción para DSH

- **Rama:** `cdv/plan-produccion-dsh`. Base de producto `75c1f35`.
- **Entrega:** [manual inicial](../produccion/00-EMPIEZA-AQUI.md), contratos para producto y operación, 85 sugerencias reconciliadas con su idShort, dos perfiles DSH, revisión independiente y notificación directa por Telegram. Los pasos de Carlos están en [PendientesCarlos](../../PendientesCarlos.md).
- **Evidencia:** verificador local aprobado (Gitleaks y 16 pruebas del MVP); 183 pruebas de backend aprobadas; 33 pruebas aisladas del notificador aprobadas. Verificado el modo preview sin llavero ni red. Ambos parches se compusieron con la CLI de Arquimedes. Los ejemplos SQL se aplicaron en PostgreSQL 16.16 local con datos ficticios; el rol de aplicación observó sólo su tienda y cero filas sin contexto después de commit y rollback.
- **Límites:** el paquete prepara el trabajo del producto. La ejecución de DSH sobre los paquetes, emparejamiento privado real, nueva credencial SMTP, instalación en teléfono, altas comerciales, pruebas bancarias y despliegue corresponden a sus hitos. Sin operaciones sobre producción.
