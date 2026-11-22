package mx.abarpay.mobile

import android.content.Intent
import android.net.Uri
import android.util.Base64
import kotlinx.coroutines.runBlocking
import mx.abarpay.mobile.persistence.KeyProvider
import okhttp3.FormBody
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Protocol
import okhttp3.Response
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config
import java.security.MessageDigest
import javax.crypto.KeyGenerator

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35])
class OwnerOidcClientTest {
    @Test
    fun systemBrowserPkceSurvivesRestartAndOnlyExchangesTheMatchingState() = runBlocking {
        val app = RuntimeEnvironment.getApplication()
        val key = KeyGenerator.getInstance("AES").apply { init(256) }.generateKey()
        val keyProvider = object : KeyProvider { override fun getOrCreate() = key }
        val config = OwnerOidcConfig("owner.example.test", "client-simulado", "api-simulado")
        var now = 1700L
        var exchanges = 0
        var verifier: String? = null
        val client = OkHttpClient.Builder().addInterceptor { chain ->
            val request = chain.request()
            assertEquals("https://owner.example.test/oauth/token", request.url.toString())
            val form = request.body as FormBody
            val fields = (0 until form.size).associate { form.name(it) to form.value(it) }
            assertEquals("authorization_code", fields["grant_type"])
            assertEquals("client-simulado", fields["client_id"])
            assertEquals("code-simulado", fields["code"])
            assertFalse(fields.containsKey("client_secret"))
            verifier = fields["code_verifier"]
            exchanges++
            Response.Builder().request(request).protocol(Protocol.HTTP_1_1)
                .code(200).message("OK")
                .body(
                    """{"access_token":"SIMULADO","token_type":"Bearer","expires_in":300}"""
                        .toResponseBody("application/json".toMediaType())
                ).build()
        }.build()
        val original = OwnerOidcClient(app, config, keyProvider, client) { now }
        val intent = original.beginSignIn()
        assertEquals(Intent.ACTION_VIEW, intent.action)
        val authorize = requireNotNull(intent.data)
        assertEquals("https", authorize.scheme)
        assertEquals("owner.example.test", authorize.host)
        assertEquals("/authorize", authorize.path)
        assertEquals("S256", authorize.getQueryParameter("code_challenge_method"))
        assertEquals("api-simulado", authorize.getQueryParameter("audience"))
        val callback = Uri.parse(authorize.getQueryParameter("redirect_uri"))
        val state = authorize.getQueryParameter("state")
        val returned = callback.buildUpon().appendQueryParameter("code", "code-simulado")
        val restarted = OwnerOidcClient(app, config, keyProvider, client) { now }

        assertTrue(runCatching { restarted.completeSignIn(returned.appendQueryParameter("state", "wrong").build()) }.isFailure)
        assertEquals(0, exchanges)
        val accepted = callback.buildUpon().appendQueryParameter("code", "code-simulado")
            .appendQueryParameter("state", state).build()
        assertEquals("SIMULADO", restarted.completeSignIn(accepted))
        assertEquals(1, exchanges)
        val digest = MessageDigest.getInstance("SHA-256").digest(requireNotNull(verifier).toByteArray())
        val challenge = Base64.encodeToString(digest, Base64.URL_SAFE or Base64.NO_PADDING or Base64.NO_WRAP)
        assertEquals(authorize.getQueryParameter("code_challenge"), challenge)
        assertTrue(runCatching { restarted.completeSignIn(accepted) }.isFailure)
        assertEquals(1, exchanges)
        assertEquals("SIMULADO", original.accessToken())
        assertFalse(app.getSharedPreferences("abarpay_owner_oidc", 0).all.toString().contains("SIMULADO"))
        now += 301
        assertNull(original.accessToken())
    }
}
