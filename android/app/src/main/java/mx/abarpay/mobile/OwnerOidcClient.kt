package mx.abarpay.mobile

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.util.Base64
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import mx.abarpay.mobile.persistence.AndroidKeystoreKeyProvider
import mx.abarpay.mobile.persistence.Ciphertext
import mx.abarpay.mobile.persistence.CryptoBox
import mx.abarpay.mobile.persistence.KeyProvider
import okhttp3.FormBody
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject
import java.security.MessageDigest
import java.security.SecureRandom
import java.util.concurrent.TimeUnit

internal data class OwnerOidcConfig(val issuer: String, val clientId: String, val audience: String)

/** Public native client; Auth0 login stays in the system browser. */
internal class OwnerOidcClient(
    context: Context,
    private val config: OwnerOidcConfig,
    keyProvider: KeyProvider = AndroidKeystoreKeyProvider("abarpay_owner_oidc_v1"),
    private val client: OkHttpClient = OkHttpClient.Builder()
        .followRedirects(false)
        .followSslRedirects(false)
        .retryOnConnectionFailure(false)
        .callTimeout(15, TimeUnit.SECONDS)
        .build(),
    private val seconds: () -> Long = { System.currentTimeMillis() / 1000L },
) {
    private val prefs = context.applicationContext.getSharedPreferences("abarpay_owner_oidc", Context.MODE_PRIVATE)
    private val crypto by lazy { CryptoBox(keyProvider.getOrCreate()) }
    private val pendingKey = "pending"
    private val accessKey = "access"
    private val callbackUri = Uri.parse(BuildConfig.APPLICATION_ID + "://oidc/callback")
    private val exchangeLock = Mutex()
    private val issuer = config.issuer.trim().let { raw ->
        val supplied = if (raw.startsWith("https://")) raw else "https://" + raw
        supplied.toHttpUrl().also {
            require(it.isHttps && it.encodedPath == "/" && it.fragment == null && it.query == null &&
                it.username.isEmpty() && it.password.isEmpty()
            ) { "La configuración de inicio de sesión no es válida." }
        }
    }
    private val scope = listOf(issuer.toString(), config.clientId, config.audience).joinToString("\n")

    fun beginSignIn(): Intent {
        require(config.clientId.isNotBlank() && config.audience.isNotBlank()) {
            "El inicio de sesión todavía no está configurado."
        }
        val state = randomCode()
        val verifier = randomCode()
        save(
            pendingKey, JSONObject()
                .put("scope", scope)
                .put("state", state)
                .put("verifier", verifier)
                .put("expiresAt", seconds() + 600L),
        )
        val challenge = base64Url(MessageDigest.getInstance("SHA-256").digest(verifier.toByteArray(Charsets.US_ASCII)))
        val authorization = issuer.newBuilder().addPathSegment("authorize")
            .addQueryParameter("response_type", "code")
            .addQueryParameter("client_id", config.clientId)
            .addQueryParameter("audience", config.audience)
            .addQueryParameter("scope", "openid profile email")
            .addQueryParameter("redirect_uri", callbackUri.toString())
            .addQueryParameter("state", state)
            .addQueryParameter("code_challenge", challenge)
            .addQueryParameter("code_challenge_method", "S256")
            .build()
        return Intent(Intent.ACTION_VIEW, Uri.parse(authorization.toString())).addCategory(Intent.CATEGORY_BROWSABLE)
    }

    suspend fun completeSignIn(callback: Uri): String = exchangeLock.withLock {
        withContext(Dispatchers.IO) {
            require(callback.scheme == callbackUri.scheme && callback.authority == callbackUri.authority &&
                callback.path == callbackUri.path
            ) { "No se reconoció el regreso desde el navegador." }
            val pending = read(pendingKey)
            val state = callback.getQueryParameters("state").singleOrNull()
            require(pending != null && pending.optString("scope") == scope &&
                pending.optLong("expiresAt") > seconds() && state != null &&
                MessageDigest.isEqual(state.toByteArray(), pending.getString("state").toByteArray())
            ) { "Este intento de inicio de sesión venció. Vuelve a entrar." }
            val code = callback.getQueryParameters("code").singleOrNull()?.takeIf { it.isNotBlank() }
                ?: error("El navegador no completó el inicio de sesión. Vuelve a entrar.")
            val request = Request.Builder().url(issuer.newBuilder().addPathSegments("oauth/token").build())
                .post(FormBody.Builder()
                    .add("grant_type", "authorization_code")
                    .add("client_id", config.clientId)
                    .add("code", code)
                    .add("redirect_uri", callbackUri.toString())
                    .add("code_verifier", pending.getString("verifier"))
                    .build()
                ).build()
            client.newCall(request).execute().use { response ->
                check(response.isSuccessful) { "No se pudo verificar el acceso. Vuelve a entrar." }
                val result = JSONObject(response.body?.string().orEmpty())
                val token = result.optString("access_token")
                val expiresIn = result.optLong("expires_in")
                check(token.isNotBlank() && expiresIn in 1..2_592_000 &&
                    result.optString("token_type").equals("Bearer", ignoreCase = true)
                ) { "No se recibió un acceso válido. Vuelve a entrar." }
                val credentials = JSONObject().put("scope", scope)
                    .put("token", token)
                    .put("expiresAt", seconds() + expiresIn)
                check(prefs.edit().putString(accessKey, encrypt(credentials)).remove(pendingKey).commit()) {
                    "No se pudo guardar el acceso en este teléfono."
                }
                token
            }
        }
    }

    fun accessToken(): String? {
        val access = read(accessKey) ?: return null
        if (access.optString("scope") != scope || access.optLong("expiresAt") <= seconds()) return null
        return access.optString("token").takeIf { it.isNotBlank() }
    }

    fun clearAccessToken() {
        check(prefs.edit().remove(accessKey).remove(pendingKey).commit()) {
            "No se pudo cerrar el acceso en este teléfono."
        }
    }

    private fun save(key: String, value: JSONObject) {
        check(prefs.edit().putString(key, encrypt(value)).commit()) {
            "No se pudo guardar el intento de inicio de sesión."
        }
    }

    private fun encrypt(value: JSONObject) = crypto.encrypt(value.toString().toByteArray()).encode()

    private fun read(key: String): JSONObject? {
        val stored = prefs.getString(key, null) ?: return null
        return runCatching { JSONObject(String(crypto.decrypt(Ciphertext.decode(stored)), Charsets.UTF_8)) }.getOrNull()
    }

    private fun randomCode(): String = base64Url(ByteArray(32).apply { SecureRandom().nextBytes(this) })

    private fun base64Url(bytes: ByteArray): String =
        Base64.encodeToString(bytes, Base64.URL_SAFE or Base64.NO_PADDING or Base64.NO_WRAP)
}
