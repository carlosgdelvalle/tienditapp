package mx.abarpay.mobile

import android.content.SharedPreferences
import mx.abarpay.mobile.persistence.saleIdFromEventId
import org.json.JSONArray
import org.json.JSONObject

/**
 * Intención de cobro en efectivo pendiente de confirmación. Se guarda de forma
 * duradera ANTES de despachar el cobro en línea, para que un cierre de la app
 * entre el envío y la respuesta conserve la misma clave y se pueda recuperar.
 */
internal data class PendingCashCheckout(
    val eventId: String,
    val employeeId: Int,
    val storeId: String,
    val server: String,
    val cart: List<CartLine>,
    val totalCents: Long,
    val cashReceivedCents: Long?,
    val catalogVersion: Long,
)

private const val PENDING_CASH_KEY = "pending_cash_checkout"

/** Escribe la intención y la marca de «creando» en una única transacción verificada. */
internal fun writePendingCashCheckout(prefs: SharedPreferences, p: PendingCashCheckout): Boolean {
    val items = JSONArray()
    p.cart.forEach { items.put(JSONObject().put("productId", it.productId).put("qtyMilli", it.qtyMilli)) }
    val json = JSONObject()
        .put("eventId", p.eventId)
        .put("employeeId", p.employeeId)
        .put("storeId", p.storeId)
        .put("server", p.server)
        .put("totalCents", p.totalCents)
        .put("cashReceivedCents", p.cashReceivedCents ?: JSONObject.NULL)
        .put("catalogVersion", p.catalogVersion)
        .put("items", items)
    return prefs.edit()
        .putString(PENDING_CASH_KEY, json.toString())
        .putBoolean("creating", true)
        .commit()
}

internal fun readPendingCashCheckout(prefs: SharedPreferences): PendingCashCheckout? {
    val raw = prefs.getString(PENDING_CASH_KEY, null) ?: return null
    return runCatching {
        val o = JSONObject(raw)
        val itemsArr = o.optJSONArray("items") ?: JSONArray()
        val cart = (0 until itemsArr.length()).map { i ->
            val line = itemsArr.getJSONObject(i)
            CartLine(line.getInt("productId"), line.getInt("qtyMilli"))
        }
        PendingCashCheckout(
            eventId = o.getString("eventId"),
            employeeId = o.getInt("employeeId"),
            storeId = o.getString("storeId"),
            server = o.getString("server"),
            cart = cart,
            totalCents = o.getLong("totalCents"),
            cashReceivedCents = if (o.isNull("cashReceivedCents")) null else o.getLong("cashReceivedCents"),
            catalogVersion = o.getLong("catalogVersion"),
        )
    }.getOrNull()
}

internal fun clearPendingCashCheckout(prefs: SharedPreferences) {
    prefs.edit().remove(PENDING_CASH_KEY).commit()
}

/**
 * Recupera una intención pendiente tras un reinicio. Solo la convierte en un
 * evento del diario si el backend actual coincide; si el evento ya existe no lo
 * duplica, y si el append falla conserva la intención para reintentarlo.
 */
internal fun recoverPendingCashCheckout(
    prefs: SharedPreferences,
    coordinator: SaleCoordinator,
    currentServer: String,
): String? {
    val pending = readPendingCashCheckout(prefs) ?: return null
    if (pending.server != currentServer) return null
    coordinator.attach(pending.storeId)
    val saleId = saleIdFromEventId(pending.eventId)
    // El evento ya fue reconocido por el servidor: solo falta recuperar el recibo.
    if (coordinator.outbox().isAckedByEventId(pending.eventId)) {
        return saleId
    }
    // El evento ya está en el diario (sin reconocer): se conserva para el replay.
    if (coordinator.outbox().pending().any { it.eventId == pending.eventId }) {
        return saleId
    }
    val appended = runCatching {
        coordinator.finalizeOfflineCashSale(
            employeeId = pending.employeeId,
            cart = pending.cart,
            totalCents = pending.totalCents,
            cashReceivedCents = pending.cashReceivedCents ?: pending.totalCents,
            catalogVersion = pending.catalogVersion,
            eventId = pending.eventId,
        )
    }.isSuccess
    // La intención pendiente solo se limpia al persistir el recibo; un fallo la
    // conserva para reintentarlo en el siguiente arranque.
    return if (appended) saleId else null
}

