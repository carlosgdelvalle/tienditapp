package mx.abarpay.mobile.persistence

import android.content.ContentValues
import android.content.Context
import android.database.Cursor
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import org.json.JSONArray
import org.json.JSONObject

/**
 * Encrypted, atomic, append-only outbox (frozen contract 1.0).
 *
 * Invariants enforced here:
 * 1. One durable operation = one outbox row. [append] inserts the row and runs
 *    the local state mutation in the *same* SQLite transaction: there is no
 *    event without state and no state without an event.
 * 2. Exactly-one-durable-operation. Each row carries a stable ULID
 *    [OutboxEntry.eventId]; resend never changes it, so the server dedupes.
 * 3. Receipts gate deletion. [markAcked] runs only after the server confirms an
 *    operation, and [purgeAcked] deletes only acked rows. Nothing is ever
 *    deleted on a timeout.
 * 4. Resumption is ordered. [pending] returns unacked rows in ascending
 *    [OutboxEntry.sequence] order; the database survives restarts and updates
 *    because it lives in internal storage and migrates per schema version.
 *
 * The payload is AES-256-GCM encrypted at rest (see [CryptoBox]); the plaintext
 * never appears in the database file.
 */
class AtomicOutbox private constructor(
    private val helper: OutboxDatabase,
    private val crypto: CryptoBox,
    val deviceId: String,
    val tenantId: String,
    val storeId: String,
) {

    companion object {
        const val DB_NAME = "abarpay_outbox.db"
        const val DB_VERSION = 1
        private const val LEASE_KEY = "offline_lease"
        private const val SNAPSHOT_KEY = "price_snapshot"

        /**
         * Open (or create) the outbox for one device. The key comes from
         * Android Keystore by default; inject a [KeyProvider] in tests.
         */
        fun open(
            context: Context,
            deviceId: String,
            tenantId: String,
            storeId: String,
            keyProvider: KeyProvider = AndroidKeystoreKeyProvider(),
        ): AtomicOutbox {
            val helper = OutboxDatabase(context.applicationContext)
            return AtomicOutbox(helper, CryptoBox(keyProvider.getOrCreate()), deviceId, tenantId, storeId)
        }
    }

    // -- Enqueue -----------------------------------------------------------

    /**
     * Append one operation atomically with its local state mutation.
     *
     * The sequence is assigned inside the same transaction as the insert, so
     * it is monotonic per device; the [eventId] ULID is generated once here
     * and passed to [applyState] so the local state can be linked to it.
     */
    @Synchronized
    fun append(
        type: String,
        occurredAt: Long,
        catalogVersion: Long,
        payload: Map<String, Any?>,
        eventId: String? = null,
        applyState: (SQLiteDatabase, String) -> Unit,
    ): EnqueuedEvent {
        val stableId = eventId ?: newUlid()
        val db = helper.writableDatabase
        db.beginTransaction()
        try {
            val sequence = (db.rawQuery(
                "SELECT COALESCE(MAX(sequence), 0) + 1 FROM outbox", null
            ).use { cursor -> cursor.moveToFirst(); cursor.getLong(0) })

            val plainJson = (mapToJson(payload) as JSONObject).toString()
            val ciphertext = crypto.encrypt(
                plainJson.toByteArray(Charsets.UTF_8)
            ).encode()

            val values = ContentValues().apply {
                put("sequence", sequence)
                put("event_id", stableId)
                put("device_id", deviceId)
                put("tenant_id", tenantId)
                put("store_id", storeId)
                put("event_type", type)
                put("catalog_version", catalogVersion)
                put("occurred_at", occurredAt)
                put("payload_cipher", ciphertext)
                put("acked", OUTBOX_NOT_ACKED)
                put("created_at", System.currentTimeMillis() / 1000)
            }
            db.insertOrThrow("outbox", null, values)

            applyState(db, stableId)
            db.setTransactionSuccessful()
            return EnqueuedEvent(sequence, stableId)
        } finally {
            db.endTransaction()
        }
    }

    /** Finalize an offline cash sale: outbox event + local sale + local stock. */
    @Synchronized
    fun appendSale(
        items: List<SaleItem>,
        employeeId: Int,
        totalCents: Long,
        cashReceivedCents: Long?,
        catalogVersion: Long,
        reference: String,
        occurredAt: Long = System.currentTimeMillis() / 1000,
        eventId: String? = null,
    ): EnqueuedEvent {
        val payload: Map<String, Any?> = buildMap {
            put("employeeId", employeeId)
            put("items", items.map { mapOf("productId" to it.productId, "qtyMilli" to it.qtyMilli) })
            put("paymentMethod", "cash")
            if (cashReceivedCents != null) put("cashReceivedCents", cashReceivedCents)
            put("reference", reference)
        }
        return append(EVENT_SALE_CREATED, occurredAt, catalogVersion, payload, eventId = eventId) { db, eventId ->
            db.insertOrThrow(
                "local_sales", null,
                ContentValues().apply {
                    put("reference", reference)
                    put("event_id", eventId)
                    put("total_cents", totalCents)
                    put("status", "paid_cash")
                    put("created_at", occurredAt)
                },
            )
            for (item in items) {
                val current = localStock(db, item.productId) ?: 0
                val next = current - item.qtyMilli
                upsertStock(db, item.productId, next, occurredAt)
            }
        }
    }

    /** Record an offline inventory adjustment: outbox event + local stock move. */
    @Synchronized
    fun appendInventoryAdjust(
        productId: Int,
        deltaMilli: Int,
        employeeId: Int,
        reason: String,
        catalogVersion: Long,
        occurredAt: Long = System.currentTimeMillis() / 1000,
    ): EnqueuedEvent {
        val payload: Map<String, Any?> = mapOf(
            "employeeId" to employeeId,
            "productId" to productId,
            "deltaMilli" to deltaMilli,
            "reason" to reason,
        )
        return append(EVENT_INVENTORY_ADJUST, occurredAt, catalogVersion, payload) { db, _ ->
            val current = localStock(db, productId) ?: 0
            upsertStock(db, productId, current + deltaMilli, occurredAt)
        }
    }

    // -- Resumption --------------------------------------------------------

    /** Unacked rows in ascending sequence order (the replay order). */
    fun pending(limit: Int = 100): List<OutboxEntry> {
        val db = helper.readableDatabase
        return db.rawQuery(
            "SELECT * FROM outbox WHERE acked = ? ORDER BY sequence ASC LIMIT ?",
            arrayOf(OUTBOX_NOT_ACKED.toString(), limit.toString()),
        ).use { cursor ->
            buildList {
                while (cursor.moveToNext()) add(toEntry(cursor))
            }
        }
    }

    /** The exact JSON array the server replays, decrypted and in order. */
    fun pendingEventsJson(limit: Int = 100): String {
        val array = JSONArray()
        pending(limit).forEach { entry -> array.put(JSONObject(entry.toEventJson())) }
        return array.toString()
    }

    fun lastAckedSequence(): Long {
        val db = helper.readableDatabase
        return db.rawQuery(
            "SELECT COALESCE(MAX(sequence), 0) FROM outbox WHERE acked = ?",
            arrayOf(OUTBOX_ACKED.toString()),
        ).use { cursor -> cursor.moveToFirst(); cursor.getLong(0) }
    }

    // -- Receipts gate deletion --------------------------------------------

    /** Mark an operation as server-confirmed; only then is it purgable. */
    @Synchronized
    fun markAcked(sequence: Long, receiptJson: String?) {
        val values = ContentValues().apply { put("acked", OUTBOX_ACKED) }
        if (receiptJson != null) values.put("receipt", receiptJson)
        helper.writableDatabase.update(
            "outbox", values, "sequence = ?", arrayOf(sequence.toString())
        )
    }

    /** Delete only server-confirmed rows; a timeout never deletes anything. */
    @Synchronized
    fun purgeAcked(): Int =
        helper.writableDatabase.delete("outbox", "acked = ?", arrayOf(OUTBOX_ACKED.toString()))

    fun isAcked(sequence: Long): Boolean {
        val db = helper.readableDatabase
        return db.rawQuery(
            "SELECT acked FROM outbox WHERE sequence = ?", arrayOf(sequence.toString())
        ).use { cursor -> cursor.moveToFirst() && cursor.getInt(0) == OUTBOX_ACKED }
    }

    // -- Lease and snapshot --------------------------------------------------

    fun saveLease(lease: OfflineLease) = saveKv(Companion.LEASE_KEY, lease.toJson())
    fun loadLease(): OfflineLease? = loadKv(Companion.LEASE_KEY)?.let(OfflineLease::fromJson)

    fun saveSnapshot(snapshot: PriceSnapshot) = saveKv(Companion.SNAPSHOT_KEY, snapshot.toJson())
    fun loadSnapshot(): PriceSnapshot? =
        loadKv(Companion.SNAPSHOT_KEY)?.let(PriceSnapshot::fromJson)

    // -- Local state --------------------------------------------------------

    fun localStock(productId: Int): Int? = localStock(helper.readableDatabase, productId)

    /**
     * Seed the projected local stock from the last-synced inventory (the price
     * snapshot carries prices only, never a balance). The checkout flow calls
     * this before selling offline; afterwards [appendSale] keeps it in sync.
     */
    @Synchronized
    fun setLocalStock(productId: Int, stockMilli: Int) {
        upsertStock(helper.writableDatabase, productId, stockMilli, System.currentTimeMillis() / 1000)
    }

    fun localSale(reference: String): LocalSale? {
        val db = helper.readableDatabase
        return db.rawQuery(
            "SELECT * FROM local_sales WHERE reference = ?", arrayOf(reference)
        ).use { cursor ->
            if (!cursor.moveToFirst()) null
            else LocalSale(
                reference = cursor.getString(cursor.getColumnIndexOrThrow("reference")),
                eventId = cursor.getString(cursor.getColumnIndexOrThrow("event_id")),
                totalCents = cursor.getLong(cursor.getColumnIndexOrThrow("total_cents")),
                status = cursor.getString(cursor.getColumnIndexOrThrow("status")),
                createdAt = cursor.getLong(cursor.getColumnIndexOrThrow("created_at")),
            )
        }
    }

    fun close() = helper.close()

    // -- Internals ----------------------------------------------------------

    private fun saveKv(key: String, value: String) {
        helper.writableDatabase.insertWithOnConflict(
            "kv", null,
            ContentValues().apply { put("key", key); put("value", value) },
            SQLiteDatabase.CONFLICT_REPLACE,
        )
    }

    private fun loadKv(key: String): String? {
        val db = helper.readableDatabase
        return db.rawQuery("SELECT value FROM kv WHERE key = ?", arrayOf(key)).use { cursor ->
            if (cursor.moveToFirst()) cursor.getString(0) else null
        }
    }

    private fun localStock(db: SQLiteDatabase, productId: Int): Int? {
        return db.rawQuery(
            "SELECT stock_milli FROM local_stock WHERE product_id = ?",
            arrayOf(productId.toString()),
        ).use { cursor -> if (cursor.moveToFirst()) cursor.getInt(0) else null }
    }

    private fun upsertStock(db: SQLiteDatabase, productId: Int, stockMilli: Int, updatedAt: Long) {
        db.insertWithOnConflict(
            "local_stock", null,
            ContentValues().apply {
                put("product_id", productId)
                put("stock_milli", stockMilli)
                put("updated_at", updatedAt)
            },
            SQLiteDatabase.CONFLICT_REPLACE,
        )
    }

    private fun toEntry(cursor: Cursor): OutboxEntry {
        val ciphertext = Ciphertext.decode(
            cursor.getString(cursor.getColumnIndexOrThrow("payload_cipher"))
        )
        val plain = crypto.decrypt(ciphertext).toString(Charsets.UTF_8)
        @Suppress("UNCHECKED_CAST")
        val payload = jsonToValue(JSONObject(plain)) as Map<String, Any?>
        return OutboxEntry(
            sequence = cursor.getLong(cursor.getColumnIndexOrThrow("sequence")),
            eventId = cursor.getString(cursor.getColumnIndexOrThrow("event_id")),
            deviceId = cursor.getString(cursor.getColumnIndexOrThrow("device_id")),
            tenantId = cursor.getString(cursor.getColumnIndexOrThrow("tenant_id")),
            storeId = cursor.getString(cursor.getColumnIndexOrThrow("store_id")),
            type = cursor.getString(cursor.getColumnIndexOrThrow("event_type")),
            catalogVersion = cursor.getLong(cursor.getColumnIndexOrThrow("catalog_version")),
            occurredAt = cursor.getLong(cursor.getColumnIndexOrThrow("occurred_at")),
            payload = payload,
            acked = cursor.getInt(cursor.getColumnIndexOrThrow("acked")) == OUTBOX_ACKED,
            receiptJson = if (cursor.isNull(cursor.getColumnIndexOrThrow("receipt"))) null
                else cursor.getString(cursor.getColumnIndexOrThrow("receipt")),
            createdAt = cursor.getLong(cursor.getColumnIndexOrThrow("created_at")),
        )
    }
}

/**
 * SQLite helper with a versioned, non-destructive migration scaffold. Adding a
 * version appends a migration to [MIGRATIONS]; pending rows survive an upgrade
 * because no migration drops the [AtomicOutbox] tables.
 */
private class OutboxDatabase(context: Context) :
    SQLiteOpenHelper(context, AtomicOutbox.DB_NAME, null, AtomicOutbox.DB_VERSION) {

    override fun onCreate(db: SQLiteDatabase) {
        db.execSQL(
            """
            CREATE TABLE IF NOT EXISTS outbox (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                device_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                store_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                catalog_version INTEGER NOT NULL,
                occurred_at INTEGER NOT NULL,
                payload_cipher TEXT NOT NULL,
                acked INTEGER NOT NULL DEFAULT 0,
                receipt TEXT,
                created_at INTEGER NOT NULL
            )
            """.trimIndent(),
        )
        db.execSQL("CREATE INDEX IF NOT EXISTS idx_outbox_pending ON outbox(acked, sequence)")
        db.execSQL(
            """
            CREATE TABLE IF NOT EXISTS local_sales (
                reference TEXT PRIMARY KEY,
                event_id TEXT NOT NULL,
                total_cents INTEGER NOT NULL,
                status TEXT NOT NULL,
                created_at INTEGER NOT NULL
            )
            """.trimIndent(),
        )
        db.execSQL(
            """
            CREATE TABLE IF NOT EXISTS local_stock (
                product_id INTEGER PRIMARY KEY,
                stock_milli INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """.trimIndent(),
        )
        db.execSQL(
            """
            CREATE TABLE IF NOT EXISTS kv (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """.trimIndent(),
        )
    }

    override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) {
        for (version in oldVersion + 1..newVersion) {
            MIGRATIONS[version]?.invoke(db)
        }
    }

    companion object {
        /** version -> non-destructive migration. Empty for v1 (nothing older). */
        private val MIGRATIONS: Map<Int, (SQLiteDatabase) -> Unit> = emptyMap()
    }
}
