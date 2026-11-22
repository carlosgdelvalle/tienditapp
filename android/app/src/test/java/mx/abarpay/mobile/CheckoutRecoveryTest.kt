package mx.abarpay.mobile

import mx.abarpay.mobile.persistence.KeyProvider
import mx.abarpay.mobile.persistence.saleIdFromEventId
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35])
class CheckoutRecoveryTest {
    private val app get() = RuntimeEnvironment.getApplication()
    private val prefs get() = app.getSharedPreferences("development_session", 0)

    @Before fun clearSession() { assertTrue(prefs.edit().clear().commit()) }

    private fun coordinator() = SaleCoordinator(app, FakeKeyProvider())

    private fun pending(
        eventId: String = "01HXRETRY00000000000000001",
        storeId: String = "tiendita-esquina",
        server: String = "http://127.0.0.1:8000",
        cart: List<CartLine> = listOf(CartLine(1, 1000)),
    ) = PendingCashCheckout(
        eventId = eventId,
        employeeId = 1,
        storeId = storeId,
        server = server,
        cart = cart,
        totalCents = 1800,
        cashReceivedCents = 2000,
        catalogVersion = 1,
    )

    @Test fun saleIdMirrorsTheServerFolio() {
        assertEquals(
            "sale_01hxretry00000000000000001",
            saleIdFromEventId("01HXRETRY00000000000000001"),
        )
        assertEquals("sale_abc123", saleIdFromEventId("ABC-123"))
    }

    @Test fun pendingIntentIsWrittenWithTheCreatingFlagInOneCommit() {
        assertTrue(writePendingCashCheckout(prefs, pending()))
        assertTrue(prefs.getBoolean("creating", false))
        assertNotNull(prefs.getString("pending_cash_checkout", null))
    }

    @Test fun recoveryEnqueuesTheSameKeyAfterRestart() {
        assertTrue(writePendingCashCheckout(prefs, pending()))
        val coord = coordinator()
        assertEquals(
            "sale_01hxretry00000000000000001",
            recoverPendingCashCheckout(prefs, coord, "http://127.0.0.1:8000"),
        )
        val events = coord.outbox().pending()
        assertEquals(1, events.size)
        assertEquals("01HXRETRY00000000000000001", events.single().eventId)
        // La intención se conserva hasta persistir el recibo.
        assertNotNull(readPendingCashCheckout(prefs))
    }

    @Test fun recoveryIgnoresADifferentBackend() {
        assertTrue(writePendingCashCheckout(prefs, pending(server = "http://a.example")))
        val coord = coordinator()
        coord.attach("tiendita-esquina")
        assertNull(recoverPendingCashCheckout(prefs, coord, "http://b.example"))
        assertNotNull(readPendingCashCheckout(prefs))
        assertEquals(0, coord.outbox().pending().size)
    }

    @Test fun recoveryDoesNotDuplicateAnExistingOutboxRow() {
        assertTrue(writePendingCashCheckout(prefs, pending()))
        val coord = coordinator()
        // La operación previa ya quedó en el diario (crash entre append y limpieza).
        coord.attach("tiendita-esquina")
        coord.finalizeOfflineCashSale(
            employeeId = 1,
            cart = listOf(CartLine(1, 1000)),
            totalCents = 1800,
            cashReceivedCents = 2000,
            catalogVersion = 1,
            eventId = "01HXRETRY00000000000000001",
        )
        assertNotNull(recoverPendingCashCheckout(prefs, coord, "http://127.0.0.1:8000"))
        assertEquals(1, coord.outbox().pending().size)
        // No se duplica y la intención se conserva hasta persistir el recibo.
        assertNotNull(readPendingCashCheckout(prefs))
    }

    @Test fun recoveryRetainsTheIntentWhenTheAppendFails() {
        // Carrito vacío fuerza require(...) en finalizeOfflineCashSale.
        assertTrue(writePendingCashCheckout(prefs, pending(cart = emptyList())))
        val coord = coordinator()
        assertNull(recoverPendingCashCheckout(prefs, coord, "http://127.0.0.1:8000"))
        assertNotNull(readPendingCashCheckout(prefs))
    }

    private class FakeKeyProvider : KeyProvider {
        private val key: SecretKey = KeyGenerator.getInstance("AES").apply { init(256) }.generateKey()
        override fun getOrCreate(): SecretKey = key
    }
}

