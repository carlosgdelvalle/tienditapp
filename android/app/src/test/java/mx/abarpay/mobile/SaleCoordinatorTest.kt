package mx.abarpay.mobile

import kotlinx.coroutines.runBlocking
import mx.abarpay.mobile.persistence.KeyProvider
import mx.abarpay.mobile.persistence.OfflineLease
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.SocketPolicy
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config
import java.io.IOException
import java.util.concurrent.TimeUnit
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35])
class SaleCoordinatorTest {

    @Test
    fun offlineCashSaleIsFinalizedLocally() {
        val app = RuntimeEnvironment.getApplication()
        val coordinator = SaleCoordinator(app, FakeKeyProvider())
        coordinator.attach("tiendita-esquina")

        coordinator.seedLocalStock(listOf(Product(1, "Coca-Cola 600 ml", "pieza", 1800, 24000)))
        val result = coordinator.finalizeOfflineCashSale(
            employeeId = 1,
            cart = listOf(CartLine(1, 2000)),
            totalCents = 3600,
            cashReceivedCents = 4000,
            catalogVersion = 1,
        )

        assertTrue(result.reference.startsWith("V-"))
        assertTrue(result.eventId.isNotBlank())
        // Un evento pendiente, tipo sale.created, con venta local y stock local.
        val pending = coordinator.outbox().pending()
        assertEquals(1, pending.size)
        assertEquals("sale.created", pending.single().type)
        assertEquals(24000 - 2000, coordinator.outbox().localStock(1))
        assertNotNull(coordinator.outbox().localSale(result.reference))
    }

    @Test
    fun replayMarksServerConfirmedEventsAsAcked() = runBlocking {
        val app = RuntimeEnvironment.getApplication()
        val server = MockWebServer()
        server.start()
        try {
            val base = server.url("/").toString().trimEnd('/')
            val coordinator = SaleCoordinator(app, FakeKeyProvider())
            coordinator.attach("tiendita-esquina")

            coordinator.outbox().saveLease(
                OfflineLease(
                    v = 1,
                    tenantId = "tiendita-esquina",
                    storeId = "tiendita-esquina",
                    deviceId = coordinator.deviceId,
                    membershipId = "mem-" + coordinator.deviceId,
                    issuedAt = 1000L,
                    expiresAt = 1000L + 12 * 3600,
                    signature = "sig",
                )
            )
            val result = coordinator.finalizeOfflineCashSale(
                employeeId = 1,
                cart = listOf(CartLine(1, 1000)),
                totalCents = 1800,
                cashReceivedCents = 2000,
                catalogVersion = 1,
            )

            val ack = JSONObject()
                .put("sequence", result.sequence)
                .put("eventId", result.eventId)
                .put("applied", true)
                .put("duplicate", false)
                .put("conflict", false)
            val body = JSONObject()
                .put("acks", JSONArray().put(ack))
                .put("nextSequence", 2)
                .toString()
            server.enqueue(MockResponse().setResponseCode(200).setBody(body))

            val sync = coordinator.replay(base)

            assertEquals(1, sync.sent)
            assertEquals(1, sync.acked)
            assertEquals(0, sync.rejected)
            assertTrue(coordinator.outbox().pending().isEmpty())
            assertTrue(coordinator.outbox().isAcked(result.sequence))
        } finally {
            server.shutdown()
        }
    }

    @Test
    fun lostAcknowledgmentKeepsTheSameSaleAcrossOutboxReopen() = runBlocking {
        val app = RuntimeEnvironment.getApplication()
        val keys = FakeKeyProvider()
        val store = "tienda-reintento"
        val first = SaleCoordinator(app, keys)
        val restarted = SaleCoordinator(app, keys)
        MockWebServer().use { server ->
            try {
                val base = server.url("/").toString().trimEnd('/')
                first.attach(store)
                val now = System.currentTimeMillis() / 1000
                first.outbox().saveLease(
                    OfflineLease(
                        tenantId = store,
                        storeId = store,
                        deviceId = first.deviceId,
                        membershipId = "mem-" + first.deviceId,
                        issuedAt = now - 10,
                        expiresAt = now + 3600,
                        signature = "SIMULADO",
                    )
                )
                first.seedLocalStock(listOf(Product(1, "Producto SIMULADO", "pieza", 1800, 24000)))
                val sale = first.finalizeOfflineCashSale(
                    employeeId = 1,
                    cart = listOf(CartLine(1, 1000)),
                    totalCents = 1800,
                    cashReceivedCents = 2000,
                    catalogVersion = 1,
                )
                server.enqueue(MockResponse().setSocketPolicy(SocketPolicy.DISCONNECT_AFTER_REQUEST))
                assertTrue(runCatching { first.replay(base) }.exceptionOrNull() is IOException)
                val original = requireNotNull(server.takeRequest(5, TimeUnit.SECONDS))
                assertEquals(sale.eventId, first.outbox().pending().single().eventId)
                first.close()

                restarted.attach(store)
                assertEquals(sale.eventId, restarted.outbox().pending().single().eventId)
                assertNotNull(restarted.outbox().localSale(sale.reference))
                val ack = JSONObject()
                    .put("sequence", sale.sequence)
                    .put("eventId", sale.eventId)
                    .put("applied", false)
                    .put("duplicate", true)
                server.enqueue(MockResponse().setBody(JSONObject().put("acks", JSONArray().put(ack)).toString()))

                assertEquals(1, restarted.replay(base).acked)
                val replay = requireNotNull(server.takeRequest(5, TimeUnit.SECONDS))
                assertEquals("/api/sync/events", replay.path)
                assertEquals(original.body.readUtf8(), replay.body.readUtf8())
                assertEquals(23000, restarted.outbox().localStock(1))
                assertTrue(restarted.outbox().pending().isEmpty())
            } finally {
                first.close()
                restarted.close()
            }
        }
    }

    private class FakeKeyProvider : KeyProvider {
        private val key: SecretKey = KeyGenerator.getInstance("AES").apply { init(256) }.generateKey()
        override fun getOrCreate(): SecretKey = key
    }
}
