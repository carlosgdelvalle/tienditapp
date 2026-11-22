package mx.abarpay.mobile

import kotlinx.coroutines.runBlocking
import mx.abarpay.mobile.persistence.KeyProvider
import mx.abarpay.mobile.persistence.saleIdFromEventId
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.Assert.assertEquals
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config
import java.util.concurrent.TimeUnit
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35])
class CheckoutIdempotencyTest {
    private val app get() = RuntimeEnvironment.getApplication()

    @Before fun clearSession() {
        app.getSharedPreferences("development_session", 0).edit().clear().commit()
    }

    @Test fun postIdempotencyKeyEqualsTheOutboxEventId() = runBlocking {
        val server = MockWebServer()
        server.start()
        try {
            val base = server.url("/").toString().trimEnd('/')
            server.enqueue(
                MockResponse().setResponseCode(200).setBody(
                    """{"saleId":"sale_01hxretry00000000000000001","id":"sale_01hxretry00000000000000001","totalCents":1800,"chargedCents":1800,"status":"paid_cash","paymentMethod":"cash","cashReceivedCents":2000,"changeCents":200}"""
                )
            )

            // El cobro en línea manda la clave estable como Idempotency-Key.
            val eventId = "01HXRETRY00000000000000001"
            val repo = ApiRepository(base)
            repo.create(1, listOf(CartLine(1, 1000)), "cash", 2000, null, eventId)
            val request = requireNotNull(server.takeRequest(5, TimeUnit.SECONDS))
            assertEquals("/api/sales", request.path)
            assertEquals(eventId, request.getHeader("Idempotency-Key"))

            // La misma clave queda durada en el diario offline.
            val coordinator = SaleCoordinator(app, FakeKeyProvider())
            coordinator.attach("tiendita-esquina")
            coordinator.finalizeOfflineCashSale(
                employeeId = 1,
                cart = listOf(CartLine(1, 1000)),
                totalCents = 1800,
                cashReceivedCents = 2000,
                catalogVersion = 1,
                eventId = eventId,
            )
            assertEquals(eventId, coordinator.outbox().pending().single().eventId)

            // Ambos caminos resuelven al mismo folio determinista del servidor.
            assertEquals("sale_01hxretry00000000000000001", saleIdFromEventId(eventId))
        } finally {
            server.shutdown()
        }
    }

    private class FakeKeyProvider : KeyProvider {
        private val key: SecretKey = KeyGenerator.getInstance("AES").apply { init(256) }.generateKey()
        override fun getOrCreate(): SecretKey = key
    }
}

