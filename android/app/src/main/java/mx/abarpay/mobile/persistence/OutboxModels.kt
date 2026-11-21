package mx.abarpay.mobile.persistence

import org.json.JSONArray
import org.json.JSONObject

/**
 * Data model for the offline journal (frozen contract 1.0).
 *
 * One durable operation = one [OutboxEntry] row; every entry carries a stable
 * idempotency key ([OutboxEntry.eventId], a ULID) and is replayed in sequence
 * order. The server acknowledges each applied operation with a receipt, and the
 * client only deletes an entry after that receipt (never on a timeout).
 */

const val EVENT_SALE_CREATED = "sale.created"
const val EVENT_INVENTORY_ADJUST = "inventory.adjust"

const val OUTBOX_NOT_ACKED = 0
const val OUTBOX_ACKED = 1

/** A signed 12-hour offline authorization lease from the server. */
data class OfflineLease(
    val v: Int = 1,
    val tenantId: String,
    val storeId: String,
    val deviceId: String,
    val membershipId: String,
    val issuedAt: Long,
    val expiresAt: Long,
    val signature: String,
) {
    fun isExpired(nowSeconds: Long): Boolean = nowSeconds > expiresAt

    fun toJson(): String = JSONObject()
        .put("v", v)
        .put("tenantId", tenantId)
        .put("storeId", storeId)
        .put("deviceId", deviceId)
        .put("membershipId", membershipId)
        .put("issuedAt", issuedAt)
        .put("expiresAt", expiresAt)
        .put("signature", signature)
        .toString()

    companion object {
        fun fromJson(raw: String): OfflineLease {
            val o = JSONObject(raw)
            return OfflineLease(
                v = o.optInt("v", 1),
                tenantId = o.getString("tenantId"),
                storeId = o.getString("storeId"),
                deviceId = o.getString("deviceId"),
                membershipId = o.getString("membershipId"),
                issuedAt = o.getLong("issuedAt"),
                expiresAt = o.getLong("expiresAt"),
                signature = o.optString("signature"),
            )
        }
    }
}

/** One catalog line of the signed price snapshot. Prices come from the server. */
data class SnapshotItem(
    val productId: Int,
    val unit: String,
    val priceCents: Long,
    val unlimitedStock: Boolean,
)

/** Signed canonical price snapshot; the offline sale never uses a local price. */
data class PriceSnapshot(
    val v: Int = 1,
    val catalogVersion: Long,
    val asOf: Long,
    val expiresAt: Long,
    val items: List<SnapshotItem>,
    val signature: String,
) {
    fun toJson(): String = JSONObject()
        .put("v", v)
        .put("catalogVersion", catalogVersion)
        .put("asOf", asOf)
        .put("expiresAt", expiresAt)
        .put("items", JSONArray().apply {
            items.forEach { item ->
                put(
                    JSONObject()
                        .put("productId", item.productId)
                        .put("unit", item.unit)
                        .put("priceCents", item.priceCents)
                        .put("unlimitedStock", item.unlimitedStock)
                )
            }
        })
        .put("signature", signature)
        .toString()

    companion object {
        fun fromJson(raw: String): PriceSnapshot {
            val o = JSONObject(raw)
            val itemsArray = o.optJSONArray("items") ?: JSONArray()
            val items = (0 until itemsArray.length()).map { index ->
                val line = itemsArray.getJSONObject(index)
                SnapshotItem(
                    productId = line.getInt("productId"),
                    unit = line.getString("unit"),
                    priceCents = line.getLong("priceCents"),
                    unlimitedStock = line.optBoolean("unlimitedStock", false),
                )
            }
            return PriceSnapshot(
                v = o.optInt("v", 1),
                catalogVersion = o.optLong("catalogVersion", 0L),
                asOf = o.optLong("asOf", 0L),
                expiresAt = o.optLong("expiresAt", 0L),
                items = items,
                signature = o.optString("signature"),
            )
        }
    }
}

/** A sale line recorded offline: product id plus quantity in milli-units. */
data class SaleItem(val productId: Int, val qtyMilli: Int)

/** A durable outbox entry as persisted locally. */
data class OutboxEntry(
    val sequence: Long,
    val eventId: String,
    val deviceId: String,
    val tenantId: String,
    val storeId: String,
    val type: String,
    val catalogVersion: Long,
    val occurredAt: Long,
    val payload: Map<String, Any?>,
    val acked: Boolean,
    val receiptJson: String?,
    val createdAt: Long,
) {
    /** The exact envelope the server replays (one operation = one event). */
    fun toEventJson(): String = JSONObject()
        .put("v", 1)
        .put("eventId", eventId)
        .put("deviceId", deviceId)
        .put("sequence", sequence)
        .put("type", type)
        .put("tenantId", tenantId)
        .put("storeId", storeId)
        .put("catalogVersion", catalogVersion)
        .put("occurredAt", occurredAt)
        .put("payload", mapToJson(payload))
        .toString()
}

/** Result of enqueueing one operation: the stable id plus its sequence. */
data class EnqueuedEvent(val sequence: Long, val eventId: String)

/** A locally finalized cash sale, coupled 1:1 to its outbox event. */
data class LocalSale(
    val reference: String,
    val eventId: String,
    val totalCents: Long,
    val status: String,
    val createdAt: Long,
)

/** Recursively turns plain Kotlin values into org.json values. */
fun mapToJson(value: Any?): Any = when (value) {
    null -> JSONObject.NULL
    is Map<*, *> -> JSONObject().apply {
        value.forEach { (key, nested) -> put(key.toString(), mapToJson(nested)) }
    }
    is List<*> -> JSONArray().apply { value.forEach { put(mapToJson(it)) } }
    is Float -> value.toDouble()
    is Boolean, is Int, is Long, is Double, is String -> value
    else -> value.toString()
}

/** Recursively turns org.json values back into plain Kotlin values. */
fun jsonToValue(value: Any?): Any? = when (value) {
    null, JSONObject.NULL -> null
    is JSONObject -> value.keys().asSequence().associate { key ->
        key to jsonToValue(value.get(key))
    }
    is JSONArray -> (0 until value.length()).map { jsonToValue(value.get(it)) }
    else -> value
}
