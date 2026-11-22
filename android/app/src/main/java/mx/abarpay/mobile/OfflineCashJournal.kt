package mx.abarpay.mobile

import android.content.Context
import android.os.SystemClock
import android.provider.Settings
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import mx.abarpay.mobile.persistence.AndroidKeystoreKeyProvider
import mx.abarpay.mobile.persistence.Ciphertext
import mx.abarpay.mobile.persistence.CryptoBox
import org.json.JSONArray
import org.json.JSONObject
import java.nio.ByteBuffer
import java.security.MessageDigest
import java.util.UUID

internal data class OfflineCashState(
    val lease: JSONObject? = null,
    val pending: List<JSONObject> = emptyList(),
    val receipt: JSONObject? = null,
)

internal data class CashDraft(val quantities: Map<String, Int> = emptyMap(), val cash: String = "")

internal class OfflineCashJournal(context: Context, baseUrl: String, tenantId: String) {
    private val app = context.applicationContext
    private val prefs = app.getSharedPreferences("abarpay_offline_cash", Context.MODE_PRIVATE)
    private val key = "$baseUrl:$tenantId"
    private val draftKey = "$key:draft"
    private val crypto by lazy { CryptoBox(AndroidKeystoreKeyProvider().getOrCreate()) }

    val hasSavedState: Boolean get() = prefs.contains(key)

    suspend fun read(): OfflineCashState = withContext(Dispatchers.IO) {
        val data = readEntry(key) ?: return@withContext OfflineCashState()
        OfflineCashState(data.optJSONObject("lease"), data.getJSONArray("pending").objects(), data.optJSONObject("receipt"))
    }

    suspend fun readDraft(): CashDraft = withContext(Dispatchers.IO) {
        val data = readEntry(draftKey) ?: return@withContext CashDraft()
        val quantities = data.getJSONObject("quantities")
        CashDraft(quantities.keys().asSequence().associateWith { quantities.getInt(it) }, data.getString("cash"))
    }

    // The small draft is committed before the edit is reflected in the UI.
    // A process killed immediately after a tap can reopen what the cashier saw.
    fun saveDraft(draft: CashDraft) {
        if (draft.quantities.isEmpty() && draft.cash.isEmpty()) {
            clearDraft()
            return
        }
        val data = JSONObject().put("quantities", JSONObject(draft.quantities)).put("cash", draft.cash)
        check(prefs.edit().putString(draftKey, encodeEntry(draftKey, data)).commit())
    }

    fun clearDraft() {
        if (prefs.contains(draftKey)) check(prefs.edit().remove(draftKey).commit())
    }

    suspend fun save(state: OfflineCashState, clearDraft: Boolean = false) = withContext(Dispatchers.IO) {
        val data = JSONObject().put("lease", state.lease)
            .put("pending", JSONArray(state.pending)).put("receipt", state.receipt)
        val editor = prefs.edit().putString(key, encodeEntry(key, data))
        if (clearDraft) editor.remove(draftKey)
        check(editor.commit())
    }

    private fun readEntry(entry: String): JSONObject? {
        val raw = prefs.getString(entry, null) ?: return null
        val data = JSONObject(crypto.decrypt(Ciphertext.decode(raw)).decodeToString())
        check(data.getString("scope") == entry)
        return data
    }

    private fun encodeEntry(entry: String, data: JSONObject) =
        crypto.encrypt(data.put("scope", entry).toString().encodeToByteArray()).encode()

    fun anchor(lease: JSONObject): JSONObject = lease
        .put("wallAtFetch", System.currentTimeMillis())
        .put("elapsedAtFetch", SystemClock.elapsedRealtime())
        .put("bootAtFetch", bootCount())

    fun occurredAt(lease: JSONObject?): Long? {
        if (lease == null) return null
        val boot = bootCount()
        val elapsed = if (boot >= 0 && boot == lease.getInt("bootAtFetch")) {
            SystemClock.elapsedRealtime() - lease.getLong("elapsedAtFetch")
        } else {
            System.currentTimeMillis() - lease.getLong("wallAtFetch")
        }
        if (elapsed < 0) return null
        val now = lease.getLong("serverTime") + elapsed / 1000
        return now.takeIf { it in lease.getLong("issuedAt")..lease.getLong("expiresAt") }
    }

    private fun bootCount() = Settings.Global.getInt(app.contentResolver, Settings.Global.BOOT_COUNT, -1)
}

/** The PostgreSQL receipt uses RFC 9562 UUID v5 with tenant namespace and checkout key. */
internal fun cashSaleId(tenantId: String, key: String): String {
    val tenant = UUID.fromString(tenantId)
    val namespace = ByteBuffer.allocate(16).putLong(tenant.mostSignificantBits)
        .putLong(tenant.leastSignificantBits).array()
    val digest = MessageDigest.getInstance("SHA-1")
    digest.update(namespace)
    val id = digest.digest(key.encodeToByteArray())
    id[6] = ((id[6].toInt() and 0x0f) or 0x50).toByte()
    id[8] = ((id[8].toInt() and 0x3f) or 0x80).toByte()
    val bytes = ByteBuffer.wrap(id)
    return UUID(bytes.long, bytes.long).toString()
}
