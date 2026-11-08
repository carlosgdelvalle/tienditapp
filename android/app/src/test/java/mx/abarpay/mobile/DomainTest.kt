package mx.abarpay.mobile

import org.junit.Assert.*
import org.junit.Test

class DomainTest {
    private val catalog = listOf(
        Product(1, "Coca-Cola 600 ml", "pieza", 1800, 24000),
        Product(4, "Huevo (kg)", "kg", 4500, 10000),
        Product(9, "Tortillas (kg)", "kg", 2600, 8000),
    )

    @Test fun quantitiesAreBoundedAndZeroRemovesLine() {
        val cart = changeQuantity(emptyList(), 1, 2000)
        assertEquals(listOf(CartLine(1, 2000)), cart)
        assertEquals(emptyList<CartLine>(), changeQuantity(cart, 1, -2000))
        assertEquals(listOf(CartLine(1, 500)), changeQuantity(cart, 1, -1500))
        assertTrue(runCatching { changeQuantity(cart, 1, 1_000_000) }.isFailure)
        assertTrue(runCatching { changeQuantity(cart, 1, -3000) }.isFailure)
    }

    @Test fun estimateUsesOnlyCatalogCents() {
        assertEquals(4501L, cartEstimate(listOf(CartLine(1, 2000), CartLine(9, 1000)),
            listOf(Product(1, "A", "pieza", 1800, 36), Product(9, "B", "kg", 901, 1))))
    }

    @Test fun milliQuantitiesRoundLineTotals() {
        assertEquals(1300L, lineTotalCents(2600, 500))
        assertEquals(3600L, lineTotalCents(1800, 2000))
        assertEquals(1125L, lineTotalCents(4500, 250))
        assertEquals(45L, lineTotalCents(1800, 25))
    }

    @Test fun quantityTextShowsKilosAndPieces() {
        assertEquals("0.5 kg", qtyText(500, "kg"))
        assertEquals("2 kg", qtyText(2000, "kg"))
        assertEquals("0.25 kg", qtyText(250, "kg"))
        assertEquals("2 pza", qtyText(2000, "pieza"))
        assertEquals("0 pza", qtyText(0, "pieza"))
    }

    @Test fun halfUnitLinesCanBeDecrementedToZero() {
        assertEquals(-500, decrementStep(500))
        assertEquals(-1000, decrementStep(1500))
        assertEquals(0, decrementStep(0))
        assertEquals(emptyList<CartLine>(), changeQuantity(listOf(CartLine(9, 500)), 9, decrementStep(500)))
    }

    @Test fun unknownProductCannotBePriced() {
        assertTrue(runCatching { cartEstimate(listOf(CartLine(99, 1000)), emptyList()) }.isFailure)
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

    @Test fun cashInputParsesPesosToCents() {
        assertEquals(10000L, parseCashCents("100"))
        assertEquals(10050L, parseCashCents("100.5"))
        assertEquals(10050L, parseCashCents("100.50"))
        assertEquals(25000L, parseCashCents("$250"))
        assertEquals(123450L, parseCashCents("1,234.50"))
        assertEquals(2500L, parseCashCents("25,00"))
        assertNull(parseCashCents(""))
        assertNull(parseCashCents("abc"))
        assertNull(parseCashCents("10.999"))
    }

    @Test fun onlyServerStatusesCountAsSettled() {
        listOf("pending", "por_conciliar", "failed", "expired", "canceled").forEach {
            assertFalse(it, Sale("s1", 1800, 1, status = it).settled)
        }
        assertTrue(Sale("s1", 1800, 1800, status = "paid_cash").settled)
        assertTrue(Sale("s1", 1800, 1, status = "paid_pey").settled)
        assertTrue(Sale("s1", 1800, 1800, status = "credit").settled)
    }

    @Test fun transportAndServerErrorsCannotUnlockRetry() {
        listOf(408, 409, 429, 500, 501, 502, 503, 504).forEach { assertFalse(it.toString(), definitelyRejected(it)) }
        listOf(400, 401, 403, 404, 422).forEach { assertTrue(it.toString(), definitelyRejected(it)) }
    }

    @Test fun expiryOnlyHidesQrAndNeverConfirmsPayment() {
        val sale = Sale("s1", 1800, 1, paymentMethod = PAYMENT_PEY, expiresAt = 100.0)
        assertTrue(canDisplayQr(sale, 99.0, false))
        assertFalse(canDisplayQr(sale, 100.0, false))
        assertFalse(canDisplayQr(sale, 99.0, true))
        assertFalse(canDisplayQr(sale.copy(paymentMethod = PAYMENT_CASH), 99.0, false))
        assertFalse(sale.paid)
    }

    @Test fun demoParserUnderstandsEverydayPhrases() {
        val result = demoParse("dos cocas y medio kilo de tortillas", catalog)
        assertEquals(2, result.items.size)
        val coke = result.items.first { it.productId == 1 }
        assertEquals(2000, coke.qtyMilli)
        assertEquals(3600L, coke.lineTotalCents)
        val tortillas = result.items.first { it.productId == 9 }
        assertEquals(500, tortillas.qtyMilli)
        assertEquals(1300L, tortillas.lineTotalCents)
        assertTrue(result.unmatched.isEmpty())

        val grams = demoParse("250 gramos de huevo", catalog).items.single()
        assertEquals(250, grams.qtyMilli)
        assertEquals("kg", grams.unit)
    }

    @Test fun moneyRetainsCentavos() { assertTrue(money(1).contains("0.01")) }

    @Test fun statusAndMethodLabelsAreSpanish() {
        assertEquals("Efectivo", methodLabel(PAYMENT_CASH))
        assertEquals("PEY / CoDi", methodLabel(PAYMENT_PEY))
        assertEquals("Fiado", methodLabel(PAYMENT_FIADO))
        assertEquals("Pagada con PEY", statusLabel("paid_pey"))
        assertEquals("A crédito (fiado)", statusLabel("credit"))
    }
}
