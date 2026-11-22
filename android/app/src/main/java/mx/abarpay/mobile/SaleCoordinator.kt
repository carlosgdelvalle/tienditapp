package mx.abarpay.mobile

import android.content.Context
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import mx.abarpay.mobile.persistence.AndroidKeystoreKeyProvider
import mx.abarpay.mobile.persistence.AtomicOutbox
import mx.abarpay.mobile.persistence.KeyProvider
import mx.abarpay.mobile.persistence.OfflineLease
import mx.abarpay.mobile.persistence.PriceSnapshot
import mx.abarpay.mobile.persistence.SaleItem
import mx.abarpay.mobile.persistence.newUlid
import mx.abarpay.mobile.persistence.resolveDeviceId
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject
import java.util.concurrent.TimeUnit

/**
 * Glues the offline cash-sale path to the encrypted, atomic outbox.
 *
 * One coordinator per device owns:
 *  - the stable per-install [deviceId] (the server binds it to one tenant forever),
 *  - the 12-hour signed offline lease and the signed price snapshot, and
 *  - the replay of pending outbox events to POST /api/sync/events.
 *
 * The online path (ApiRepository.create) stays untouched; this coordinator is
 * only consulted when the server is unreachable and for the reconnect replay.
 */
class SaleCoordinator(
    private val context: Context,
    private val keyProvider: KeyProvider = AndroidKeystoreKeyProvider(),
) {
    private val client = OkHttpClient.Builder()
        .retryOnConnectionFailure(false)
        .followRedirects(false)
        .followSslRedirects(false)
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(25, TimeUnit.SECONDS)
        .writeTimeout(25, TimeUnit.SECONDS)
        .callTimeout(35, TimeUnit.SECONDS)
        .build()

    private var storeId: String? = null
    private var box: AtomicOutbox? = null

    /** Stable per-install identity; generated once and persisted in SharedPreferences. */
    val deviceId: String get() = resolveDeviceId(context)

    /** Bind this coordinator to a store; re-opening only when the store changes. */
    fun attach(storeId: String) {
        val clean = storeId.trim()
        if (clean.isBlank() || this.storeId == clean) return
        box?.close()
        box = null
        this.storeId = clean
    }

    /** Lazily open the outbox for the bound store (tenantId == storeId in the demo). */
    internal fun outbox(): AtomicOutbox {
        val sid = checkNotNull(storeId) { "Sin tienda para el cobro sin conexión" }
        return box ?: AtomicOutbox.open(context, deviceId, sid, sid, keyProvider).also { box = it }
    }

    fun lease(): OfflineLease? = storeId?.let { outbox().loadLease() }
    fun snapshot(): PriceSnapshot? = storeId?.let { outbox().loadSnapshot() }

    /**
     * Null when an offline sale is allowed; otherwise a short user-facing reason
     * (no authorization yet, or the 12-hour lease already expired).
     */
    fun offlineBlocker(nowSeconds: Long = System.currentTimeMillis() / 1000): String? {
        val sid = storeId ?: return "Conéctate una vez para autorizar ventas sin conexión."
        val lease = outbox().loadLease() ?: return "Conéctate una vez para autorizar ventas sin conexión."
        if (lease.isExpired(nowSeconds)) return "La autorización sin conexión venció. Conéctate para renovarla."
        return null
    }

    /** Seed the projected local stock from the last-synced inventory (only once per product). */
    fun seedLocalStock(products: List<Product>) {
        val outbox = outbox()
        products.forEach { product ->
            if (outbox.localStock(product.id) == null) {
                outbox.setLocalStock(product.id, product.stockMilli)
            }
        }
    }

    /**
     * Fetch (or reuse) the signed lease and price snapshot from POST /api/sync/lease.
     * Returns true when a valid lease is available afterwards.
     */
    suspend fun acquireLease(base: String): Boolean = withContext(Dispatchers.IO) {
        val outbox = outbox()
        val existing = outbox.loadLease()
        val now = System.currentTimeMillis() / 1000
        if (existing != null && !existing.isExpired(now)) return@withContext true
        val sid = checkNotNull(storeId) { "Sin tienda para el cobro sin conexión" }
        val body = JSONObject()
            .put("deviceId", deviceId)
            .put("storeId", sid)
            .put("tenantId", sid)
            .put("membershipId", "mem-" + deviceId)
        val response = post(base, "/api/sync/lease", body)
        val leaseJson = response.optJSONObject("lease") ?: return@withContext false
        outbox.saveLease(OfflineLease.fromJson(leaseJson.toString()))
        response.optJSONObject("snapshot")?.let { snap ->
            outbox.saveSnapshot(PriceSnapshot.fromJson(snap.toString()))
        }
        true
    }

    /**
     * Finalize one offline cash sale locally: one durable outbox event plus the
     * local sale and the local stock decrement in the same SQLite transaction.
     */
    fun finalizeOfflineCashSale(
        employeeId: Int,
        cart: List<CartLine>,
        totalCents: Long,
        cashReceivedCents: Long,
        catalogVersion: Long,
        eventId: String? = null,
    ): OfflineSaleResult {
        require(cart.isNotEmpty()) { "El carrito está vacío" }
        require(totalCents > 0) { "Actualiza el catálogo antes de vender sin conexión" }
        require(cashReceivedCents >= totalCents) { "El efectivo recibido no cubre el total" }
        val reference = "V-" + newUlid().takeLast(8)
        val enqueued = outbox().appendSale(
            items = cart.map { SaleItem(it.productId, it.qtyMilli) },
            employeeId = employeeId,
            totalCents = totalCents,
            cashReceivedCents = cashReceivedCents,
            catalogVersion = catalogVersion,
            reference = reference,
            eventId = eventId,
        )
        return OfflineSaleResult(
            reference = reference,
            eventId = enqueued.eventId,
            sequence = enqueued.sequence,
            totalCents = totalCents,
        )
    }

    /**
     * Replay pending events in order to POST /api/sync/events and mark the
     * server-confirmed ones acked. Returns the batch result for the UI message.
     */
    suspend fun replay(base: String): SyncResult = withContext(Dispatchers.IO) {
        val outbox = outbox()
        val lease = outbox.loadLease() ?: return@withContext SyncResult(0, 0, 0, "Sin autorización sin conexión")
        val pending = outbox.pending(limit = 100)
        if (pending.isEmpty()) return@withContext SyncResult(0, 0, 0, null)

        val events = JSONArray()
        pending.forEach { entry -> events.put(JSONObject(entry.toEventJson())) }
        val body = JSONObject()
            .put("lease", JSONObject(lease.toJson()))
            .put("events", events)
        val response = post(base, "/api/sync/events", body)

        val acks = response.optJSONArray("acks") ?: JSONArray()
        var acked = 0
        var rejected = 0
        for (i in 0 until acks.length()) {
            val ack = acks.getJSONObject(i)
            val sequence = ack.optLong("sequence", -1L)
            val applied = ack.optBoolean("applied", false)
            val duplicate = ack.optBoolean("duplicate", false)
            // Only a server confirmation (applied, or the same event already applied)
            // gates deletion. Business rejections stay pending for review and retry.
            if (sequence >= 0 && (applied || duplicate)) {
                outbox.markAcked(sequence, ack.toString())
                acked++
            } else {
                rejected++
            }
        }
        SyncResult(pending.size, acked, rejected, null)
    }

    fun close() {
        box?.close()
        box = null
    }

    private fun post(base: String, path: String, body: JSONObject): JSONObject {
        val payload = body.toString().toByteArray(Charsets.UTF_8)
        val request = Request.Builder()
            .url(base + path)
            .header("Accept", "application/json")
            .post(payload.toRequestBody("application/json; charset=utf-8".toMediaType()))
            .build()
        client.newCall(request).execute().use { response ->
            val raw = response.body?.string().orEmpty()
            val json = if (raw.isBlank()) JSONObject() else runCatching { JSONObject(raw) }
                .getOrElse { JSONObject().put("detail", raw.take(300)) }
            if (!response.isSuccessful) {
                throw ApiFailure(
                    response.code,
                    json.optString("detail").ifBlank { "El servidor respondió " + response.code },
                )
            }
            return json
        }
    }
}

/** Result of finalizing one offline cash sale locally. */
data class OfflineSaleResult(
    val reference: String,
    val eventId: String,
    val sequence: Long,
    val totalCents: Long,
)

/** Result of replaying pending outbox events to the server. */
data class SyncResult(
    val sent: Int,
    val acked: Int,
    val rejected: Int,
    val detail: String?,
)
