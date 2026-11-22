package mx.abarpay.mobile

import android.content.Context
import android.net.Uri
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject
import java.security.KeyPair
import java.security.KeyPairGenerator
import java.security.KeyStore
import java.security.PrivateKey
import java.security.PublicKey
import java.security.Signature
import java.util.UUID

/**
 * Flujo del dueño para aprobar el QR del navegador (J-11). Vive en un archivo
 * separado del resto de la app para no acoplarse a ShopViewModel/Repository ni
 * al outbox. La app se autentica con el celular ya vinculado.
 */

/** Reto leído del QR abarpay://challenge/{id}?code=...&nonce=...&exp=...&intent=... */
data class OwnerChallenge(
    val id: String,
    val code: String,
    val nonce: String,
    val exp: String,
    val intent: String,
)

object OwnerQrParser {
    fun parse(raw: String): OwnerChallenge {
        val uri = Uri.parse(raw)
        require(uri.scheme == "abarpay" && uri.host == "challenge") {
            "El código no es un reto de Abarpay"
        }
        val id = uri.lastPathSegment?.takeIf { it.isNotBlank() }
            ?: throw IllegalArgumentException("El reto no tiene identificador")
        require(id.matches(Regex("^[A-Za-z0-9_-]+$"))) {
            "El reto tiene un identificador no válido"
        }
        val code = uri.getQueryParameter("code")
            ?: throw IllegalArgumentException("El reto no tiene código")
        val nonce = uri.getQueryParameter("nonce")
            ?: throw IllegalArgumentException("El reto no tiene nonce")
        val exp = uri.getQueryParameter("exp")
            ?: throw IllegalArgumentException("El reto no tiene expiración")
        val intent = uri.getQueryParameter("intent")
            ?: throw IllegalArgumentException("El reto no tiene propósito")
        return OwnerChallenge(id = id, code = code, nonce = nonce, exp = exp, intent = intent)
    }
}

object OwnerQrCrypto {
    /** Mensaje canónico que firma el dispositivo y re-verifica el servidor. */
    fun challengePayload(challenge: OwnerChallenge, chosenStore: String): String {
        val sep = 10.toChar().toString()
        return listOf(challenge.id, challenge.nonce, challenge.exp, challenge.intent, chosenStore)
            .joinToString(sep)
    }

    fun sign(privateKey: PrivateKey, message: String): String {
        val signer = Signature.getInstance("SHA256withRSA")
        signer.initSign(privateKey)
        signer.update(message.toByteArray(Charsets.UTF_8))
        return Base64.encodeToString(signer.sign(), Base64.NO_WRAP)
    }

    fun publicKeyPem(publicKey: PublicKey): String {
        val nl = 10.toChar().toString()
        val encoded = Base64.encodeToString(publicKey.encoded, Base64.NO_WRAP)
        return "-----BEGIN PUBLIC KEY-----" + nl + encoded + nl + "-----END PUBLIC KEY-----"
    }

    fun generateRsaKeyPair(): KeyPair {
        val generator = KeyPairGenerator.getInstance("RSA")
        generator.initialize(2048)
        return generator.generateKeyPair()
    }
}

data class OwnerStore(val tenantId: String, val name: String)

/** Cliente HTTP para preparar y aprobar el ingreso a la consola. */
class OwnerQrApi(private val baseUrl: String, private val accessToken: String) {
    fun approve(challengeId: String, deviceId: String, deviceSignature: String, code: String, tenantId: String?) {
        val body = org.json.JSONObject()
            .put("deviceSignature", deviceSignature)
            .put("code", code)
            .put("deviceId", deviceId)
        if (tenantId != null) {
            body.put("tenantId", tenantId)
        }
        val request = okhttp3.Request.Builder()
            .url(baseUrl.trimEnd('/') + "/api/auth/challenge/" + challengeId + "/approve")
            .header("Authorization", "Bearer " + accessToken)
            .post(body.toString().toRequestBody("application/json".toMediaType()))
            .build()
        okhttp3.OkHttpClient().newCall(request).execute().use { response ->
            if (!response.isSuccessful) {
                throw ApiFailure(response.code, "No se pudo aprobar el reto")
            }
        }
    }

    fun ownerStores(): List<OwnerStore> {
        val request = Request.Builder()
            .url(baseUrl.trimEnd('/') + "/api/me/memberships")
            .header("Authorization", "Bearer " + accessToken)
            .get()
            .build()
        OkHttpClient().newCall(request).execute().use { response ->
            if (!response.isSuccessful) {
                throw ApiFailure(response.code, "No se pudo cargar tu tienda.")
            }
            val items = JSONObject(checkNotNull(response.body).string()).getJSONArray("items")
            return buildList {
                for (i in 0 until items.length()) {
                    val member = items.getJSONObject(i)
                    if (member.optString("role") == "owner") {
                        add(OwnerStore(member.getString("tenantId"), member.optString("storeName")))
                    }
                }
            }
        }
    }

    /** Crea la tienda del dueño (primer acceso). */
    fun signup(name: String, storeName: String): JSONObject {
        val body = JSONObject()
            .put("name", name)
            .put("storeName", storeName)
        val request = Request.Builder()
            .url(baseUrl.trimEnd('/') + "/api/signup")
            .header("Authorization", "Bearer " + accessToken)
            .post(body.toString().toRequestBody("application/json".toMediaType()))
            .build()
        OkHttpClient().newCall(request).execute().use { response ->
            if (!response.isSuccessful) {
                throw ApiFailure(response.code, "No se pudo crear la tienda")
            }
            return JSONObject(response.body!!.string())
        }
    }
}

/** Clave RSA por dispositivo en Android Keystore (firma PKCS#1 v1.5 / SHA-256). */
object OwnerDeviceKey {
    private const val ANDROID_KEYSTORE = "AndroidKeyStore"
    private const val ALIAS = "abarpay_owner_device_v1"

    fun getOrCreate(): KeyPair {
        val keyStore = KeyStore.getInstance(ANDROID_KEYSTORE).apply { load(null) }
        (keyStore.getEntry(ALIAS, null) as? KeyStore.PrivateKeyEntry)?.let {
            return KeyPair(it.certificate.publicKey, it.privateKey)
        }
        val generator = KeyPairGenerator.getInstance(KeyProperties.KEY_ALGORITHM_RSA, ANDROID_KEYSTORE)
        generator.initialize(
            KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_SIGN)
                .setDigests(KeyProperties.DIGEST_SHA256)
                .setSignaturePaddings(KeyProperties.SIGNATURE_PADDING_RSA_PKCS1)
                .setKeySize(2048)
                .build()
        )
        return generator.generateKeyPair()
    }
}

internal fun ownerDeviceId(context: Context): String {
    val prefs = context.getSharedPreferences("abarpay_owner_device", Context.MODE_PRIVATE)
    prefs.getString("id", null)?.let { return it }
    val id = UUID.randomUUID().toString()
    prefs.edit().putString("id", id).apply()
    return id
}

internal suspend fun approveOwnerChallenge(
    context: Context,
    api: OwnerQrApi,
    challenge: OwnerChallenge,
    tenantId: String,
) = kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.IO) {
    val payload = OwnerQrCrypto.challengePayload(challenge, tenantId)
    val signature = OwnerQrCrypto.sign(OwnerDeviceKey.getOrCreate().private, payload)
    api.approve(challenge.id, ownerDeviceId(context), signature, challenge.code, tenantId)
}
