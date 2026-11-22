package mx.abarpay.mobile

import android.net.Uri
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.util.concurrent.TimeUnit

internal data class EmployeeAccess(
    val tenantId: String,
    val name: String,
    val canSell: Boolean,
    val canFiado: Boolean,
    val canInventory: Boolean,
)

internal class EmployeeApi(baseUrl: String, private val auth: OwnerAuth) {
    private val base = baseUrl.trimEnd('/')
    private val client = OkHttpClient.Builder().callTimeout(10, TimeUnit.SECONDS)
        .followRedirects(false).followSslRedirects(false).build()

    suspend fun invitation(token: String): JSONObject =
        request(invitePath(token), authenticated = false)

    suspend fun accept(token: String, name: String): JSONObject =
        request(invitePath(token) + "/accept", JSONObject().put("name", name))

    suspend fun memberships(): List<EmployeeAccess> = request("/api/me/memberships")
        .getJSONArray("items").objects()
        .filter { it.optString("role") == "employee" && it.optBoolean("active") }
        .map {
            EmployeeAccess(
                tenantId = it.getString("tenantId"),
                name = it.optString("storeName").ifBlank { it.optString("tenantName") },
                canSell = it.optBoolean("canSell"),
                canFiado = it.optBoolean("canFiado"),
                canInventory = it.optBoolean("canInventory"),
            )
        }

    suspend fun request(
        path: String,
        body: JSONObject? = null,
        key: String? = null,
        authenticated: Boolean = true,
    ): JSONObject {
        val token = if (authenticated) {
            auth.accessToken() ?: throw ApiFailure(401, "Vuelve a entrar con tu celular.")
        } else null
        return withContext(Dispatchers.IO) {
            val builder = Request.Builder().url(base + path)
            if (token != null) builder.header("Authorization", "Bearer " + token)
            if (key != null) builder.header("Idempotency-Key", key)
            if (body != null) builder.post(body.toString().toRequestBody("application/json".toMediaType()))
            client.newCall(builder.build()).execute().use { response ->
                val raw = response.body?.string().orEmpty()
                val data = runCatching { JSONObject(raw) }.getOrNull()
                if (!response.isSuccessful) {
                    val detail = data?.opt("detail") as? String
                    throw ApiFailure(response.code, detail ?: "No se pudo completar. Intenta de nuevo.")
                }
                checkNotNull(data)
            }
        }
    }

    private fun invitePath(token: String) = "/api/tenant/members/invites/" + Uri.encode(token)
}
