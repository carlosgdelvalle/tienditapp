package mx.abarpay.mobile

import android.os.Looper
import mx.abarpay.mobile.persistence.KeyProvider
import mx.abarpay.mobile.persistence.saleIdFromEventId
import okhttp3.mockwebserver.Dispatcher
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.RecordedRequest
import okhttp3.mockwebserver.SocketPolicy
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.Config
import java.util.concurrent.atomic.AtomicReference
import javax.crypto.KeyGenerator

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35])
class CashCheckoutPathTest {
    @Test fun localRetryUsesTheKeyActuallySentByCheckout() {
        val app = RuntimeEnvironment.getApplication()
        val session = app.getSharedPreferences("development_session", 0)
        val owner = app.getSharedPreferences("abarpay_owner", 0)
        assertTrue(owner.edit().putBoolean("onboarded_owner", true).putInt("employee_id", 1).commit())
        val key = KeyGenerator.getInstance("AES").apply { init(256) }.generateKey()
        val keys = object : KeyProvider { override fun getOrCreate() = key }
        val posted = AtomicReference<String>()
        val postedBody = AtomicReference<String>()
        val synced = AtomicReference<String>()
        MockWebServer().use { server ->
            server.dispatcher = object : Dispatcher() {
                override fun dispatch(request: RecordedRequest): MockResponse {
                    val response = MockResponse().setHeader("Content-Type", "application/json")
                    return when (request.path) {
                        "/api/bootstrap" -> response.setBody(
                            """{"store":{"id":"tiendita-esquina","name":"SIMULADO"},
                            "products":[{"id":1,"name":"Producto SIMULADO","unit":"pieza","priceCents":1800,"stockMilli":1000}],
                            "employees":[{"id":1,"name":"Dueña","role":"owner","canSell":true,"active":true}]}"""
                        )
                        "/api/sync/lease" -> {
                            val id = JSONObject(request.body.readUtf8()).getString("deviceId")
                            val now = System.currentTimeMillis() / 1000
                            response.setBody("""{"lease":{"tenantId":"tiendita-esquina","storeId":"tiendita-esquina",
                            "deviceId":"$id","membershipId":"mem-$id","issuedAt":$now,"expiresAt":${now+3600},"signature":"SIMULADO"},
                            "snapshot":{"catalogVersion":42,"asOf":$now,"expiresAt":${now+3600},
                            "items":[{"productId":1,"unit":"pieza","priceCents":1800}],"signature":"SIMULADO"}}""")
                        }
                        "/api/sales" -> {
                            posted.set(request.getHeader("Idempotency-Key"))
                            postedBody.set(request.body.readUtf8())
                            response.setSocketPolicy(SocketPolicy.DISCONNECT_AFTER_REQUEST)
                        }
                        "/api/sync/events" -> {
                            val event = JSONObject(request.body.readUtf8()).getJSONArray("events").getJSONObject(0)
                            val eventId = event.getString("eventId")
                            synced.set(eventId)
                            response.setBody("""{"acks":[{"eventId":"$eventId","sequence":${event.getLong("sequence")},
                            "duplicate":true,"receipt":{"saleId":"${saleIdFromEventId(eventId)}","totalCents":1800,
                            "cashReceivedCents":2000,"changeCents":200}}]}""")
                        }
                        else -> response.setResponseCode(404).setBody("""{"detail":"Sin datos de prueba"}""")
                    }
                }
            }
            val base = server.url("/").toString().trimEnd('/')
            assertTrue(session.edit().putString("server",base).commit())
            val firstCoordinator = SaleCoordinator(app, keys)
            val first = ShopViewModel(app, firstCoordinator)
            idleUntil { first.ui.value.employee != null && !first.ui.value.busy }
            first.quantity(1, 1000)
            first.payCash(2000)
            idleUntil { !first.ui.value.busy && posted.get() != null && first.ui.value.sale != null }
            assertEquals(posted.get(), firstCoordinator.outbox().pending().single().eventId)
            assertEquals(saleIdFromEventId(posted.get()), first.ui.value.sale?.id)
            val body = JSONObject(postedBody.get())
            assertEquals(1800L, body.getLong("expectedTotalCents"))
            assertEquals(42L, body.getLong("catalogVersion"))
            firstCoordinator.close()

            val restoredCoordinator = SaleCoordinator(app, keys)
            val restarted = ShopViewModel(app, restoredCoordinator)
            idleUntil { !restarted.ui.value.busy && synced.get() != null }
            assertEquals(posted.get(), synced.get())
            assertTrue(restoredCoordinator.outbox().pending().isEmpty())
            assertEquals(saleIdFromEventId(posted.get()), restarted.ui.value.sale?.id)
            restoredCoordinator.close()
        }
    }

    private fun idleUntil(condition: () -> Boolean) {
        repeat(400) {
            shadowOf(Looper.getMainLooper()).idle()
            if (condition()) return
            Thread.sleep(15)
        }
        error("No llegó el estado de checkout esperado")
    }
}
