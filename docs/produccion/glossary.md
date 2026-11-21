# Abarpay glossary · English / Español de México

Use the English column in agent briefs, contracts, and verification reports. Use the Mexican Spanish column to identify the right concept when reviewing screens or writing copy. Where a workflow already supplies an exact UI string, use that string verbatim. Keep established identifiers such as `apply_payment`, `bankAccountId`, and `fiado_entries` in code.

| English engineering term | Mexican Spanish | What the distinction changes |
|---|---|---|
| Store / tenant | tienda / negocio | One store is one isolation and billing boundary. Say *tienda* to a shopkeeper. One owner can belong to several stores. |
| Store owner / SaaS operator | dueño o dueña de la tienda / equipo de Abarpay | The owner approves web access from the phone. Internal staff authenticate separately to operate the SaaS. |
| Till / checkout | caja / cobrar | A till belongs to a store and records cash movements. Checkout is the workflow for completing a sale. |
| Charge / collect payment | generar un cobro / cobrar | Creating or displaying a CoDi QR requests payment. Only verified settlement completes that payment. |
| Payment confirmed | pago confirmado | Use the actual verification source. A screenshot or QR shown on a phone cannot establish this state. |
| Cash tendered / change due | efectivo recibido / cambio | The customer’s tender can exceed the sale total. Return the difference instead of recording it as revenue. |
| Receipt of sale | comprobante de venta | The customer’s proof of a recorded sale. A local cash receipt can exist before the phone synchronizes. |
| Customer repayment / partial repayment | pago del cliente / abono | An *abono* reduces an existing debt. A *liquidación* clears the outstanding balance. Preserve the original sale in both cases. |
| Store credit / amount owed | fiado / saldo pendiente | A sale *a fiado* creates a receivable. The ledger distinguishes it from cash collected and pey-confirmed payments. |
| Credit limit / due date | límite de fiado / fecha de vencimiento | Eligibility for another credit sale and the due date of an existing debt are separate decisions. |
| Opening float | fondo inicial de caja | Starting cash used to make change. Include it in expected cash at close and exclude it from sales. |
| Till close / cash count | corte de caja / conteo de efectivo | Closing the till reconciles expected and counted cash. The cashier can save a count offline before final handover. |
| Cash handover / owner acceptance | entrega de efectivo / aceptación de la entrega | Record who hands over the cash and who accepts it. The employee’s declaration and owner’s acceptance are separate events. |
| Variance / inventory adjustment | diferencia / ajuste de inventario | A variance records a discrepancy. An authorized adjustment changes the stock ledger and records the reason. |
| Stock on hand / stockout | existencias / producto agotado | Distinguish what the phone last observed from centrally available stock. A stockout rate needs a denominator of observed item-days. |
| Replenishment / purchase order | reposición / pedido al proveedor | A proposed or approved order precedes delivery. Placing an order does not increase available stock. |
| Goods receipt / stock posting | recepción de mercancía / entrada de inventario | Count the physical delivery first. An offline receipt can await approval before its quantities post to shared inventory. |
| Reconciliation | conciliación | Name the objects being compared: a CoDi charge against pey, a till count against expected cash, or an Abarpay subscription charge against its billing record. |
| Bank account identifier | CLABE (Clave Bancaria Estandarizada) | The merchant enters an 18-digit CLABE. Pey returns a separate account ID used for routing. Keep the full CLABE out of reports. |
| Owner sign-in QR / CoDi payment QR | QR de acceso / QR de cobro CoDi | Approving a browser session and collecting money have different actors, confirmations, and outcomes. |
| Pending sync / needs attention | pendiente de sincronización / requiere atención | Pending work can retry when connectivity returns. A discrepancy or uncertain result needs review before repeating an operation. |
| Merchant sales / SaaS revenue | ventas de la tienda / ingresos de Abarpay | Merchant payment volume and Abarpay’s subscription collections belong to separate ledgers. Label every amount and denominator. |
| Refund / credit repayment | reembolso / abono al fiado | A refund returns money previously collected. A credit repayment brings money in against a debt. |
| Activity dossier | expediente de actividad para crédito | A proposed owner-reviewed report for a named financial institution. Interest in a dossier does not count as a delivery, fee, or loan approval. |
| Explicit opt-in / withdrawal | consentimiento expreso / retiro del consentimiento | Optional data participation has a purpose and a recipient. Withdrawing it preserves free history and export. |

**Example acceptance criterion:** When an offline cash sale has been recorded on the phone, show `Cobro en efectivo guardado en el teléfono. Se sincronizará al volver la conexión.` After the app restarts, the same receipt reference must be available. Replaying the operation must leave one sale in the central ledger. See the [workflow and status-copy specification](03-flujos-y-ergonomia.md).

Keep the offer names **Gratis**, **Control**, and **Formalización**, the payment names **CoDi** and **pey**, and the fixture label **SIMULADO** as specified. For ambiguous instructions such as “verify receiving,” name the actor, object, and resulting record: verify the employee’s goods receipt against the purchase order, the owner’s acceptance of cash, or the provider’s confirmation of payment.
