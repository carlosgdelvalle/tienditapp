package mx.abarpay.mobile

import android.content.Context
import android.os.SystemClock
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.util.concurrent.TimeUnit

interface OwnerAuth {
    suspend fun accessToken(): String?
    suspend fun startEnrollment(phone: String, inviteToken: String? = null): String
    suspend fun verifyEnrollment(challengeId: String, code: String)
}

internal class OwnerPhoneAuth(context: Context, private val baseUrl: String) : OwnerAuth {
    private val app = context.applicationContext
    private val prefs = app.getSharedPreferences("abarpay_owner_device", Context.MODE_PRIVATE)
    private val client = OkHttpClient.Builder().callTimeout(10, TimeUnit.SECONDS)
        .followRedirects(false).followSslRedirects(false).build()
    private val mutex = Mutex()
    private var token: String? = null
    private var expiresAt = 0L

    override suspend fun accessToken(): String? = mutex.withLock {
        if (SystemClock.elapsedRealtime() < expiresAt) return@withLock token
        if (!prefs.getBoolean("enrollment_attempted", false)) return@withLock null
        withContext(Dispatchers.IO) {
            val deviceId = ownerDeviceId(app)
            val challenge = post("device/start", JSONObject().put("deviceId", deviceId))
                .getString("challengeId")
            val result = try {
                verify("device", challenge)
            } catch (failure: ApiFailure) {
                if (failure.code == 401) return@withContext null
                throw failure
            }
            cache(result)
        }
    }

    override suspend fun startEnrollment(phone: String, inviteToken: String?): String = withContext(Dispatchers.IO) {
        val pair = OwnerDeviceKey.getOrCreate()
        post(
            "phone/start",
            JSONObject().put("phone", phone).put("deviceId", ownerDeviceId(app))
                .put("publicKey", OwnerQrCrypto.publicKeyPem(pair.public))
                .put("inviteToken", inviteToken),
        ).getString("challengeId")
    }

    override suspend fun verifyEnrollment(challengeId: String, code: String) {
        mutex.withLock {
            withContext(Dispatchers.IO) {
                // Persist the attempt before sending it. If the response is lost,
                // the original key can prove enrollment on the next entry.
                prefs.edit().putBoolean("enrollment_attempted", true).commit()
                cache(verify("phone", challengeId, code))
            }
        }
    }

    private fun verify(method: String, challengeId: String, code: String? = null): JSONObject {
        val operation = if (method == "phone") "enroll" else "signin"
        val key = OwnerDeviceKey.getOrCreate()
        val signature = OwnerQrCrypto.sign(key.private, "abarpay-owner-$operation:$challengeId")
        val body = JSONObject().put("challengeId", challengeId).put("signature", signature)
        if (code != null) body.put("code", code)
        return post("$method/verify", body)
    }

    private fun cache(result: JSONObject): String {
        val received = result.getString("accessToken")
        token = received
        expiresAt = SystemClock.elapsedRealtime() + (result.getLong("expiresIn") - 5) * 1000
        return received
    }

    private fun post(path: String, body: JSONObject): JSONObject {
        val request = Request.Builder().url(baseUrl.trimEnd('/') + "/api/auth/owner/" + path)
            .post(body.toString().toRequestBody("application/json".toMediaType())).build()
        client.newCall(request).execute().use { response ->
            if (!response.isSuccessful) {
                val message = when (response.code) {
                    401 -> "Ese código ya no sirve o no coincide. Revísalo o pide otro."
                    403 -> "Usa el número al que te invitó la tienda. Si el enlace venció, pide otro."
                    409 -> "Este número ya está vinculado. Usa el otro celular o contacta a Abarpay."
                    422 -> "Revisa que el número y el código estén completos."
                    429 -> "Espera un momento antes de volver a intentar."
                    else -> "El servicio no respondió. Intenta de nuevo."
                }
                throw ApiFailure(response.code, message)
            }
            return JSONObject(checkNotNull(response.body).string())
        }
    }
}
