# docs · Abarpay

Documentos de trabajo del equipo para el hackatón DevDay Exchange (7-8 nov 2026). Complementan el [`README.md`](../README.md) del repo, que sigue siendo la referencia del producto y de la integración con pey.

| Archivo | Para qué sirve |
|---|---|
| [`v1-contract.md`](v1-contract.md) | Contrato de la entrega v1: datos, endpoints, dinero, cantidades y consola. |
| [`pendientes-manana.md`](pendientes-manana.md) | Pago real pendiente y decisiones para la mañana del 8-nov. |
| [`propuesta-4pm.md`](propuesta-4pm.md) | Propuesta que se entrega el sábado a las 16:00. Antes de enviarla hay que llenar la tabla de estado con lo que de verdad pasó. |
| [`plan-entrega.md`](plan-entrega.md) | Plan minuto a minuto hasta la entrega final del domingo a las 13:00, con la evidencia que cierra cada punto y el orden de recortes si vamos tarde. |
| [`plan-construccion.md`](plan-construccion.md) | Plan técnico: contratos compartidos (tablas, tipos, endpoints), bloques con dueño, tareas con sus pruebas y fallas que no pueden tronar el demo. |
| [`modelo-de-negocio.md`](modelo-de-negocio.md) | Modelo de negocio con comparables de India y Brasil. Separa hechos con fuente de hipótesis por validar. |
| [`boceto-producto.html`](boceto-producto.html) | Boceto de las pantallas (ábrelo en el navegador). Productos, montos y cifras son de ejemplo. |
| [`diseno/`](diseno/README.md) | Maquetas de Abarpay: pantallas, recorridos y sistema de diseño, con un índice descriptivo. |
| [`decisiones/`](decisiones/) | Decisiones vigentes: stack (0001), alcance del MVP (0002), credenciales y pagos (0003) y escáner (0004). |
| [`bitacora/`](bitacora/) | Una entrada por PR o hito, con evidencia. |
| [`AUDITORIA_PROTOTIPO_FASTAPI.md`](AUDITORIA_PROTOTIPO_FASTAPI.md) | Auditoría del prototipo de Ricardo. |

La entrega v1 es la app Android [`../android/`](../android/README.md) con el backend [`../server/`](../server/README.md) y la consola del dueño. El MVP anterior en [`../app/`](../app/README.md) queda como referencia. El manual para agentes y personas es [`../AGENTS.md`](../AGENTS.md).

Reglas que aplican a todo: las credenciales nunca van al repo; los pagos de prueba los hace una persona; una venta solo pasa a pagada con una confirmación verificada.
