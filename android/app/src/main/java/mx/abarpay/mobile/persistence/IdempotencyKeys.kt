package mx.abarpay.mobile.persistence

import android.content.Context
import java.security.SecureRandom

/**
 * Stable idempotency keys for the offline journal.
 *
 * The idempotency key is the ULID [newUlid] generates once per operation, at
 * enqueue time. It never changes on resend, so a retry after a lost ACK carries
 * the same key and the server deduplicates by (tenantId, deviceId, eventId).
 */

private const val CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
private val secureRandom = SecureRandom()

/**
 * A 26-character ULID: a 48-bit millisecond timestamp followed by 80 bits of
 * randomness, encoded in Crockford base32 (most significant first). It is
 * sortable by creation time and unique enough to key every operation.
 */
fun newUlid(nowMillis: Long = System.currentTimeMillis()): String {
    val entropy = ByteArray(10).also(secureRandom::nextBytes)
    val data = ByteArray(16)
    var ts = nowMillis
    for (i in 5 downTo 0) {
        data[i] = (ts and 0xFF).toByte()
        ts = ts ushr 8
    }
    entropy.copyInto(data, 6)

    val chars = CharArray(26)
    var buffer = 0
    var bufferBits = 0
    var index = 0
    for (byte in data) {
        buffer = (buffer shl 8) or (byte.toInt() and 0xFF)
        bufferBits += 8
        while (bufferBits >= 5) {
            bufferBits -= 5
            chars[index++] = CROCKFORD[(buffer ushr bufferBits) and 0x1F]
        }
    }
    if (bufferBits > 0) {
        chars[index] = CROCKFORD[(buffer shl (5 - bufferBits)) and 0x1F]
    }
    return String(chars)
}

private const val DEVICE_ID_PREFS = "abarpay_offline"
private const val DEVICE_ID_KEY = "device_id"

/**
 * A stable per-install device id, generated once and persisted. It identifies
 * this phone to the server and binds it to exactly one tenant forever.
 */
fun resolveDeviceId(context: Context): String {
    val prefs = context.getSharedPreferences(DEVICE_ID_PREFS, Context.MODE_PRIVATE)
    val existing = prefs.getString(DEVICE_ID_KEY, null)
    if (!existing.isNullOrBlank()) return existing
    val generated = "dev_" + newUlid().lowercase()
    prefs.edit().putString(DEVICE_ID_KEY, generated).apply()
    return generated
}
