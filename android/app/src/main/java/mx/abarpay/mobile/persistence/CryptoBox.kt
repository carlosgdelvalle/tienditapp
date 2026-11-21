package mx.abarpay.mobile.persistence

import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/**
 * AEAD encryption for the outbox payload: AES-256-GCM with the key held in
 * Android Keystore (never extracted). The ciphertext on disk carries a random
 * IV plus the GCM authentication tag, so a tampered event fails to decrypt and
 * is quarantined instead of silently accepted (frozen contract 1.0).
 */

private const val GCM_TAG_BITS = 128
private const val GCM_IV_BYTES = 12
const val OUTBOX_KEY_ALIAS = "abarpay_outbox_key_v1"

/** IV || (ciphertext || GCM tag), serialized as two base64 segments. */
data class Ciphertext(val iv: ByteArray, val bytes: ByteArray) {
    fun encode(): String =
        Base64.encodeToString(iv, Base64.NO_WRAP) + ":" +
            Base64.encodeToString(bytes, Base64.NO_WRAP)

    companion object {
        fun decode(raw: String): Ciphertext {
            val parts = raw.split(":", limit = 2)
            require(parts.size == 2) { "Texto cifrado mal formado" }
            return Ciphertext(
                Base64.decode(parts[0], Base64.NO_WRAP),
                Base64.decode(parts[1], Base64.NO_WRAP),
            )
        }
    }
}

class CryptoBox(private val key: SecretKey) {

    fun encrypt(plain: ByteArray): Ciphertext {
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, key)
        val iv = cipher.iv
        return Ciphertext(iv, cipher.doFinal(plain))
    }

    fun decrypt(ciphertext: Ciphertext): ByteArray {
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(
            Cipher.DECRYPT_MODE,
            key,
            GCMParameterSpec(GCM_TAG_BITS, ciphertext.iv),
        )
        return cipher.doFinal(ciphertext.bytes)
    }
}

/** Supplies the AES key; Android Keystore by default, injectable for tests. */
interface KeyProvider {
    fun getOrCreate(): SecretKey
}

/**
 * AES-256 key generated inside Android Keystore and never exported. Key
 * rotation re-encrypts with a new alias while still reading previous versions
 * (the alias is versioned by [alias]).
 */
class AndroidKeystoreKeyProvider(
    private val alias: String = OUTBOX_KEY_ALIAS,
) : KeyProvider {

    override fun getOrCreate(): SecretKey {
        val keyStore = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (keyStore.getKey(alias, null) as? SecretKey)?.let { return it }
        val generator = KeyGenerator.getInstance(
            KeyProperties.KEY_ALGORITHM_AES,
            "AndroidKeyStore",
        )
        generator.init(
            KeyGenParameterSpec.Builder(
                alias,
                KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
            )
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                .setRandomizedEncryptionRequired(true)
                .build(),
        )
        return generator.generateKey()
    }
}
