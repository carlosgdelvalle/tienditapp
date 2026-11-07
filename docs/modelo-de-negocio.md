# Abarpay · Modelo de negocio

Hackatón DevDay Exchange Community · CDMX · 7-8 nov 2026 · equipo Abarpay (pey + OpenAI)

> Estado del documento: borrador para el equipo. Lo que dice **Hecho** trae fuente. Lo que dice **Hipótesis** no está probado y el hackatón no lo prueba.

## 1. En una línea

Abarpay le cobra al tendero por CoDi sin comisión: el tendero o su empleado dicta la venta, la app arma la cuenta, genera el cobro y le avisa en voz alta cuando ya le pagaron. Cada venta queda registrada producto por producto, y ese historial es lo que después le abre crédito.

## 2. El problema

- **Hecho:** cerca del 85% de las transacciones en México fueron en efectivo en 2024 (ENIF, citada por [Mundi](https://mundi.io/finanzas/nuevas-reglas-de-banxico-para-pagos-digitales-en-2026/)).
- **Hecho:** CoDi tenía unos 22M de cuentas validadas a finales de 2025, pero solo registró 4.4M de operaciones en todo 2025 ([ClearingPost](https://clearingpost.com/insights/mexico-s-codi-logged-4-4-million-operations-in-2025-as-banxico-sets-december-sta/)). La gente lo tiene y no lo usa.
- **Hecho:** a partir del 14-dic-2026, la Circular 9/2026 obliga a los bancos a estandarizar cómo se ven CoDi, DiMo y los pagos QR en sus apps ([ClearingPost](https://clearingpost.com/insights/mexico-s-codi-logged-4-4-million-operations-in-2025-as-banxico-sets-december-sta/)). Eso mejora el lado del que paga.
- **Nuestra lectura:** el cuello de botella está del lado del que cobra. Para aceptar una transferencia, el tendero tiene que sacar el celular, abrir el banco y buscar si ya cayó, con la fila esperando. Además no sabe qué vendió ni qué le falta resurtir, porque nadie captura nada.

## 3. Para quién

Tienditas de barrio y abarrotes. Después, taqueros y puestos con ticket chico y alto volumen.

## 4. Por qué el tendero se cambia

Su competencia es el efectivo, que ya cuesta 0%. "Pagar menos comisiones" solo convence a quien ya tiene terminal de tarjeta. Para los demás, el argumento es este:

| Lo que gana | Contra el efectivo |
|---|---|
| No pierde la venta | El cliente que no trae efectivo ya no se va al Oxxo |
| No da cambio | Se acaba el "¿no tiene de 500?" |
| Menos efectivo en el cajón | Menos riesgo de asalto (sin dato duro todavía) |
| Sabe que ya le pagaron sin ver el celular | Aviso en voz alta, como en India |
| Resurte sin contar | El inventario se descuenta solo con cada venta |
| Acceso a beneficios | Descuentos de proveedor, y después crédito |

## 5. Lo que ya funciona en otros países

| Caso | Qué hace | Cómo gana dinero | Fuente |
|---|---|---|---|
| Paytm Soundbox (India, UPI) | Bocina que anuncia cada pago recibido | Renta mensual de unas ₹100-150 (dato de 2023); 15.1M de suscripciones de comercios entre QR, Soundbox y terminales | [Paytm may-2026](https://paytm.com/blog/payments/paytm-merchant-payments-network-1-51-crore-storefronts/), [BW Disrupt](https://bwdisrupt.com/article/paytm-soundbox-vs-the-rest-battle-heats-up-with-card-payment-introduction-490096) |
| BharatPe (India, UPI) | QR gratis para la kirana | Préstamos con socio regulado (NBFC), evaluados con el historial de pagos y cobrados de las ventas diarias. 7M+ comercios en 2021, captados con agentes de campo | [TechCrunch 2021](https://techcrunch.com/2021/02/10/india-fintech-bharatpe-valued-at-900-million-in-new-108-million-fundraise), [análisis](https://basicallyhow.substack.com/p/the-economics-of-bharatpe-explained) |
| InfinitePay / CloudWalk (Brasil, Pix) | El celular como terminal, Pix gratis | Comisión de tarjeta y crédito a PyMEs; R$7.16 mil millones de revenue anualizado en 2025 (dato de la empresa) | [Sacra](https://sacra.com/c/cloudwalk/), [InfinitePay](https://www.infinitepay.io/newsroom/infinitepay-lanca-pix-por-aproximacao-para-empreendedores-que-usam-o-celular-como-maquininha) |
| BEES / AB InBev (México) | App B2B donde la tiendita hace sus pedidos | ~70% del revenue de AB InBev en México | [Digital Commerce 360](https://www.digitalcommerce360.com/2025/05/08/ab-inbev-b2b-digital-sales-revenue-q1-fy25/) |

Patrón: **el pago gratis atrae al comercio y el dinero sale del crédito.** Ninguno de los casos de pago sabe *qué* se vendió, solo *cuánto*. Ese es nuestro hueco.

## 6. Modelo de ingresos

El tendero no paga por cobrar con CoDi. Las fuentes de ingreso, de más probada a menos:

1. **Crédito vía socio regulado (ingreso principal, fase 3).** Con meses de ventas verificables, producto por producto, armamos un perfil de buena gestión. Un SOFOM o banco presta y nosotros cobramos comisión por originación. Nosotros no prestamos ni tocamos el dinero. Probado por BharatPe e InfinitePay. **Hipótesis:** que el detalle por producto mejore el riesgo frente a ver solo montos.
2. **Plan Pro para el tendero (fase 2).** Renta mensual baja por funciones extra: reportes, varios usuarios, alertas de resurtido. El precedente es la renta del Soundbox. **Hipótesis:** el precio que aguanta un tendero en México.
3. **Datos agregados para marcas (fase 2).** Sell-out por zona y por categoría, anónimo y agregado, nunca por tienda identificable sin consentimiento. **Hipótesis:** que las marcas paguen por esto. Es la fuente menos probada.
4. **Pedidos a proveedores como socio, no competencia (fase 2).** El inventario detecta "te quedan 3 Cocas" y manda el pedido a BEES o a otro proveedor, y cobramos comisión por referencia. No competimos con BEES, que ya tiene ese canal.

## 7. Cómo llegamos a las tienditas

- **Hecho:** BharatPe creció con agentes de campo tienda por tienda. Una app no se adopta sola en el canal tradicional.
- **Canales candidatos (hipótesis):** SEDECO CDMX (co-organizador del evento y cliente de pey), los repartidores de las marcas que ya visitan cada tiendita, y referidos entre tenderos.
- **Primer mercado:** una colonia de CDMX, 50 tienditas, con medición de uso semanal.

## 8. Por qué pey, por qué ahora

- pey ya resolvió la conexión con Banxico: es tercero desarrollador aprobado y no custodia fondos, porque el pago va de banco a banco ([pey](https://pey.mx/codi), [aviso de privacidad](https://pey.mx/legal/aviso-de-privacidad)).
- A pey le faltan voz, IA, aviso de pago y cualquier cosa del canal de tienditas. Abarpay es un canal de distribución para su API.
- El 14-dic, con la Circular 9/2026, el lado del que paga se vuelve más fácil. El que llegue primero con la herramienta del que cobra se queda el canal.

## 9. Riesgos

| Riesgo | Mitigación |
|---|---|
| El tendero teme que el SAT lo fiscalice con sus datos | Los datos son suyos y él decide compartirlos; a terceros solo va información agregada |
| Que la IA entienda mal un producto dictado | El tendero confirma con un toque antes de cobrar; el error nunca le llega al cliente |
| Dependencia de pey: su API es gratis "por el momento" | Arquitectura con el proveedor de CoDi intercambiable |
| Datos personales (teléfono, CLABE, audio dictado) | El audio se transcribe y no se guarda; aviso de privacidad; cumplimiento de la LFPDPPP |
| Prestar sin licencia | Solo referimos a socios regulados |
| pey aún no tiene sandbox | Pruebas con $0.01 MXN reales hechas por una persona; las API keys solo en `.env` |

## 10. Qué tiene que ser cierto (lo que validamos después del hackatón)

1. El tendero usa el cobro por voz más de 10 veces al día durante 4 semanas.
2. La captura por voz acierta en al menos 90% de las ventas de una tiendita real, medido con frases reales.
3. Un socio regulado acepta evaluar crédito con nuestro historial.
4. Una marca o distribuidor paga por los datos agregados de una colonia.

## 11. Fases

- **Fase 1 · Hackatón (hoy-mañana):** venta dictada → cobro CoDi con pey → aviso de pago en voz alta a todos los teléfonos → inventario que baja solo. Todo real, con pagos de $0.01.
- **Más adelante:** captura por cámara (gemelo digital del mostrador).
- **Fase 2 · Piloto (meses 1-3):** 50 tienditas en una colonia, Plan Pro, primeros datos agregados.
- **Fase 3 · Crédito (meses 4+):** socio regulado y originación de crédito.

## Pitch en una frase

"Paytm en India le dijo al tendero cuánto le pagaron. Nosotros le decimos qué vendió, se lo cobramos por CoDi sin comisión y con ese historial le abrimos crédito."
