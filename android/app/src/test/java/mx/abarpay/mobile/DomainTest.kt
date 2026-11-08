package mx.abarpay.mobile

import org.junit.Assert.*
import org.junit.Test

class DomainTest {
    @Test fun quantitiesAreBoundedAndZeroRemovesLine() {
        val cart = changeQuantity(emptyList(), 1, 2)
        assertEquals(listOf(CartLine(1, 2)), cart)
        assertEquals(emptyList<CartLine>(), changeQuantity(cart, 1, -2))
        assertTrue(runCatching { changeQuantity(cart, 1, 998) }.isFailure)
        assertTrue(runCatching { changeQuantity(cart, 1, -3) }.isFailure)
    }
    @Test fun estimateUsesOnlyCatalogCents() {
        assertEquals(4501L, cartEstimate(listOf(CartLine(1, 2), CartLine(2, 1)),
            listOf(Product(1, "A", 1800, 36), Product(2, "B", 901, 1))))
    }
    @Test fun unknownProductCannotBePriced() {
        assertTrue(runCatching { cartEstimate(listOf(CartLine(99, 1)), emptyList()) }.isFailure)
    }
    @Test fun httpsOnlyInReleaseAndEmulatorOnlyInDebug() {
        assertEquals("https://shop.example", normalizeServer(" https://shop.example/ ", false))
        assertEquals("http://10.0.2.2:8000", normalizeServer("http://10.0.2.2:8000", true))
        listOf("http://10.0.2.2:8000", "http://192.168.0.2:8000", "https://user:password@shop.example",
            "https://shop.example/api", "https://shop.example?token=value", "https://shop.example#secret").forEach {
            assertTrue(it, runCatching { normalizeServer(it, false) }.isFailure)
        }
        assertTrue(runCatching { normalizeServer("http://192.168.0.2:8000", true) }.isFailure)
    }
    @Test fun onlyPaidIsSuccess() {
        listOf("pending", "expired", "por_conciliar", "unknown").forEach {
            assertFalse(Sale("s1", 1800, 1, status = it).paid)
        }
        assertTrue(Sale("s1", 1800, 1, status = "paid").paid)
    }
    @Test fun transportAndServerErrorsCannotUnlockRetry() {
        listOf(408, 409, 429, 500, 502, 503, 504).forEach { assertFalse(definitelyRejected(it)) }
        listOf(400, 401, 403, 422).forEach { assertTrue(definitelyRejected(it)) }
    }
    @Test fun expiryOnlyHidesQrAndNeverConfirmsPayment() {
        val sale = Sale("s1", 1800, 1, expiresAt = 100.0)
        assertTrue(canDisplayQr(sale, 99.0, false))
        assertFalse(canDisplayQr(sale, 100.0, false))
        assertFalse(canDisplayQr(sale, 99.0, true))
        assertFalse(sale.paid)
    }
    @Test fun moneyRetainsCentavos() { assertTrue(money(1).contains("0.01")) }
}
