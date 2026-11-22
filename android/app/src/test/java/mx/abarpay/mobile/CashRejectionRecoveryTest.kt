package mx.abarpay.mobile

import android.os.Looper
import mx.abarpay.mobile.persistence.KeyProvider
import okhttp3.mockwebserver.Dispatcher
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.RecordedRequest
import okhttp3.mockwebserver.SocketPolicy
import org.json.JSONObject
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.Config
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35])
class CashRejectionRecoveryTest {
    private val app get() = RuntimeEnvironment.getApplication()

    private fun keyProvider() = object : KeyProvider {
        private val key = KeyGenerator.getInstance("AES").apply { init(256) }.generateKey()
        override fun getOrCreate(): SecretKey = key
    }

    private fun bootstrapBody() = """{"store":{"id":"tiendita-esquina","name":"SIMULADO"},
        "products":[{"id":1,"name":"Producto SIMULADO","unit":"pieza","priceCents":1800,"stockMilli":1000}],
        "employees":[{"id":1,"name":"Dueña","role":"owner","canSell":true,"active":true}]}"""

    private fun leaseBody(request: RecordedRequest): String {
        val id = JSONObject(request.body.readUtf8()).getString("deviceId")
        val now = System.currentTimeMillis() / 1000
        return """{"lease":{"tenantId":"tiendita-esquina","storeId":"tiendita-esquina",
        "deviceId":"$id","membershipId":"mem-$id","issuedAt":$now,"expiresAt":${now + 3600},"signature":"SIMULADO"},
        "snapshot":{"catalogVersion":42,"asOf":$now,"expiresAt":${now + 3600},
        "items":[{"productId":1,"unit":"pieza","priceCents":1800}],"signature":"SIMULADO"}}"""
    }

    @Test fun httpRejectionClearsBothAndCreatesNoJournalEvent() {
        val session = app.getSharedPreferences("development_session", 0)
        val owner = app.getSharedPreferences("abarpay_owner", 0)
        assertTrue(owner.edit().putBoolean("onboarded_owner", true).putInt("employee_id", 1).commit())
        val keys = keyProvider()
        MockWebServer().use { server ->
            server.dispatcher = object : Dispatcher() {
                override fun dispatch(request: RecordedRequest): MockResponse {
                    val response = MockResponse().setHeader("Content-Type", "application/json")
                    return when (request.path) {
                        "/api/bootstrap" -> response.setBody(bootstrapBody())
                        "/api/sync/lease" -> response.setBody(leaseBody(request))
                        "/api/sales" -> response.setResponseCode(422).setBody("""{"detail":"El efectivo recibido no cubre el total"}""")
                        "/api/sync/events" -> response.setBody("""{"acks":[]}""")
                        else -> response.setResponseCode(404).setBody("""{"detail":"Sin datos de prueba"}""")
                    }
                }
            }
            val base = server.url("/").toString().trimEnd('/')
            assertTrue(session.edit().putString("server", base).commit())
            val coordinator = SaleCoordinator(app, keys)
            val vm = ShopViewModel(app, coordinator)
            idleUntil { vm.ui.value.employee != null && !vm.ui.value.busy }
            vm.quantity(1, 1000)
            vm.payCash(1000)
            idleUntil { !vm.ui.value.busy && vm.ui.value.message != null }
            assertTrue(coordinator.outbox().pending().isEmpty())
            assertNull(readPendingCashCheckout(session))
            assertFalse(session.getBoolean("creating", false))
        }
    }

    @Test fun missingLeaseTransportRetainsThePendingHint() {
        val session = app.getSharedPreferences("development_session", 0)
        val owner = app.getSharedPreferences("abarpay_owner", 0)
        assertTrue(owner.edit().putBoolean("onboarded_owner", true).putInt("employee_id", 1).commit())
        val keys = keyProvider()
        MockWebServer().use { server ->
            server.dispatcher = object : Dispatcher() {
                override fun dispatch(request: RecordedRequest): MockResponse {
                    val response = MockResponse().setHeader("Content-Type", "application/json")
                    return when (request.path) {
                        "/api/bootstrap" -> response.setBody(bootstrapBody())
                        "/api/sync/lease" -> response.setResponseCode(500).setBody("""{"detail":"falla"}""")
                        "/api/sales" -> response.setSocketPolicy(SocketPolicy.DISCONNECT_AFTER_REQUEST)
                        "/api/sync/events" -> response.setBody("""{"acks":[]}""")
                        else -> response.setResponseCode(404).setBody("""{"detail":"Sin datos de prueba"}""")
                    }
                }
            }
            val base = server.url("/").toString().trimEnd('/')
            assertTrue(session.edit().putString("server", base).commit())
            val coordinator = SaleCoordinator(app, keys)
            val vm = ShopViewModel(app, coordinator)
            idleUntil { vm.ui.value.employee != null && !vm.ui.value.busy }
            vm.quantity(1, 1000)
            vm.payCash(2000)
            idleUntil { !vm.ui.value.busy && vm.ui.value.message != null }
            assertTrue(coordinator.outbox().pending().isEmpty())
            assertNotNull(readPendingCashCheckout(session))
            assertTrue(session.getBoolean("creating", false))
        }
    }

    private fun idleUntil(condition: () -> Boolean) {
        repeat(400) {
            shadowOf(Looper.getMainLooper()).idle()
            if (condition()) return
            Thread.sleep(15)
        }
        error("No llegó el estado esperado")
    }
}

