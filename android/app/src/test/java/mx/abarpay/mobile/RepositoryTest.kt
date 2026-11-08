package mx.abarpay.mobile

import kotlinx.coroutines.runBlocking
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.SocketPolicy
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.util.concurrent.TimeUnit

class RepositoryTest {
    private fun repo(server: MockWebServer) = ApiRepository(server.url("/").toString().trimEnd('/'))

    @Test fun postIsNotRetriedAfterServerReceivesItAndDisconnects() = runBlocking {
        val server = MockWebServer()
        server.start()
        try {
            server.enqueue(MockResponse().setSocketPolicy(SocketPolicy.DISCONNECT_AFTER_REQUEST))
            val repo = repo(server)
            assertTrue(runCatching { repo.create(1, listOf(CartLine(1, 1000)), PAYMENT_CASH, 5000, null) }.isFailure)
            assertEquals(1, server.requestCount)
            val request = server.takeRequest(1, TimeUnit.SECONDS)!!
            assertEquals("POST", request.method)
            assertEquals("/api/sales", request.path)
        } finally {
            server.shutdown()
        }
    }

    @Test fun postIsNotReplayedForImmediateServiceRetry() = runBlocking {
        val server = MockWebServer()
        server.start()
        try {
            server.enqueue(MockResponse().setResponseCode(503).addHeader("Retry-After", "0"))
            server.enqueue(MockResponse().setResponseCode(503))
            val repo = repo(server)
            assertTrue(runCatching { repo.create(1, listOf(CartLine(1, 1000)), PAYMENT_PEY, null, null) }.exceptionOrNull() is ApiFailure)
            assertEquals(1, server.requestCount)
        } finally {
            server.shutdown()
        }
    }

    @Test fun postRedirectIsNotFollowed() = runBlocking {
        val server = MockWebServer()
        server.start()
        try {
            server.enqueue(MockResponse().setResponseCode(307).addHeader("Location", server.url("/again")))
            val repo = repo(server)
            assertTrue(runCatching { repo.create(1, listOf(CartLine(1, 1000)), PAYMENT_PEY, null, null) }.exceptionOrNull() is ApiFailure)
            assertEquals(1, server.requestCount)
        } finally {
            server.shutdown()
        }
    }

    @Test fun saleRequestUsesOnlyContractFields() {
        val j = saleRequest(2, listOf(CartLine(4, 500)), PAYMENT_FIADO, null, 7)
        assertEquals(setOf("employeeId", "items", "paymentMethod", "customerId"), j.keys().asSequence().toSet())
        val line = j.getJSONArray("items").getJSONObject(0)
        assertEquals(setOf("productId", "qtyMilli"), line.keys().asSequence().toSet())
        assertEquals(500, line.getInt("qtyMilli"))
        assertFalse(j.has("totalCents"))
        assertFalse(j.has("priceCents"))
    }

    @Test fun cashSaleResponseKeepsChange() = runBlocking {
        val server = MockWebServer()
        server.start()
        try {
            server.enqueue(MockResponse().setBody("""{"saleId":"s1","status":"paid_cash","totalCents":3600,"chargedCents":3600,"cashReceivedCents":5000,"changeCents":1400,"paymentMethod":"cash"}"""))
            val sale = repo(server).create(2, listOf(CartLine(1, 2000)), PAYMENT_CASH, 5000, null)
            assertEquals("paid_cash", sale.status)
            assertEquals(3600L, sale.totalCents)
            assertEquals(1400L, sale.changeCents)
            assertTrue(sale.settled)
            val body = JSONObject(server.takeRequest().body.readUtf8())
            assertEquals("cash", body.getString("paymentMethod"))
            assertEquals(5000L, body.getLong("cashReceivedCents"))
        } finally {
            server.shutdown()
        }
    }

    @Test fun peyPendingResponseExposesQrAndExpiry() = runBlocking {
        val server = MockWebServer()
        server.start()
        try {
            server.enqueue(MockResponse().setBody("""{"saleId":"s2","status":"pending","totalCents":1800,"chargedCents":1,"paymentMethod":"pey","qrId":"qr-1","qrImage":"data:image/png;base64,AA==","expiresAt":1794096000.5}"""))
            val sale = repo(server).create(1, listOf(CartLine(1, 1000)), PAYMENT_PEY, null, null)
            assertEquals("pending", sale.status)
            assertEquals("qr-1", sale.qrId)
            assertEquals(1L, sale.chargedCents)
            assertTrue(canDisplayQr(sale, 1794096000.0, false))
            assertEquals(PAYMENT_PEY, sale.paymentMethod)
        } finally {
            server.shutdown()
        }
    }

    @Test fun peyTimeout202KeepsReference() = runBlocking {
        val server = MockWebServer()
        server.start()
        try {
            server.enqueue(MockResponse().setResponseCode(202).setBody("""{"saleId":"s3","status":"por_conciliar","note":"timeout"}"""))
            val sale = repo(server).create(1, listOf(CartLine(1, 1000)), PAYMENT_PEY, null, null)
            assertEquals("s3", sale.id)
            assertEquals("por_conciliar", sale.status)
            assertEquals("timeout", sale.note)
        } finally {
            server.shutdown()
        }
    }

    @Test fun peyRejection502KeepsFailedReference() = runBlocking {
        val server = MockWebServer()
        server.start()
        try {
            server.enqueue(MockResponse().setResponseCode(502).setBody("""{"saleId":"s4","status":"failed","note":"rechazado por pey"}"""))
            val sale = repo(server).create(1, listOf(CartLine(1, 1000)), PAYMENT_PEY, null, null)
            assertEquals("s4", sale.id)
            assertEquals("failed", sale.status)
            assertFalse(sale.settled)
        } finally {
            server.shutdown()
        }
    }

    @Test fun barcode404IsRecognizable() = runBlocking {
        val server = MockWebServer()
        server.start()
        try {
            server.enqueue(MockResponse().setResponseCode(404).setBody("""{"detail":"unknown barcode"}"""))
            val error = runCatching { repo(server).lookup("7509999999999") }.exceptionOrNull()
            assertTrue(error is ApiFailure)
            assertEquals(404, (error as ApiFailure).code)
        } finally {
            server.shutdown()
        }
    }

    @Test fun barcodeLookupAndLinkUseProductObjects() = runBlocking {
        val server = MockWebServer()
        server.start()
        try {
            val product = """{"id":1,"name":"Coca-Cola 600 ml","unit":"pieza","priceCents":1800,"stockMilli":24000,"lowStockMilli":5000,"quick":true}"""
            server.enqueue(MockResponse().setBody(product))
            server.enqueue(MockResponse().setBody(product))
            val repo = repo(server)
            assertEquals(1, repo.lookup("7500000000001").id)
            assertEquals(1, repo.link("7509999999999", 1).id)
            val lookupBody = JSONObject(server.takeRequest().body.readUtf8())
            assertEquals("7500000000001", lookupBody.getString("code"))
            val linkBody = JSONObject(server.takeRequest().body.readUtf8())
            assertEquals(1, linkBody.getInt("productId"))
        } finally {
            server.shutdown()
        }
    }

    @Test fun saleStatusReadsCustomerAndPaymentFields() = runBlocking {
        val server = MockWebServer()
        server.start()
        try {
            server.enqueue(MockResponse().setBody("""{"saleId":"s1","status":"credit","totalCents":1800,"chargedCents":1800,"paymentMethod":"fiado","customer":{"id":1,"name":"Mari","balanceCents":5300},"cashReceivedCents":null,"changeCents":null,"txId":null}"""))
            val sale = repo(server).status("s1")
            assertEquals("credit", sale.status)
            assertEquals(1, sale.customerId)
            assertEquals("Mari", sale.customerName)
            assertEquals(5300L, sale.customerBalanceCents)
            assertNull(sale.changeCents)
            assertEquals("/api/sales/s1", server.takeRequest().path)
        } finally {
            server.shutdown()
        }
    }

    @Test fun reportReadsV1Fields() = runBlocking {
        val server = MockWebServer()
        server.start()
        try {
            server.enqueue(MockResponse().setBody("""{"totalCents":5000,"collectedCents":3200,"cashCents":1800,"peyCents":1400,"fiadoCents":1800,"salesCount":3,"byEmployee":[{"name":"Lupita","totalCents":5000}],"topProducts":[{"name":"Coca-Cola","qtyMilli":2000,"unit":"pieza"}],"lowStock":[{"name":"Pan","stockMilli":4000,"unit":"pieza"}],"pending":1,"fiadoOutstandingCents":1800,"demoMode":true}"""))
            val report = repo(server).report()
            assertEquals(5000L, report.totalCents)
            assertEquals(3200L, report.collectedCents)
            assertEquals(1, report.pending)
            assertEquals(2000, report.topProducts.single().qtyMilli)
            assertEquals(4000, report.lowStock.single().stockMilli)
            assertTrue(report.demoMode)
        } finally {
            server.shutdown()
        }
    }

    @Test fun journalRoundTripRetainsQrAndPaymentFields() {
        val sale = Sale("s1", 1800, 1, "expired", PAYMENT_PEY, qrId = "qr-1",
            qrImage = "data:image/png;base64,AA==", expiresAt = 1200.5, txId = "tx", note = "cancelada")
        assertEquals(sale, readSale(saleJson(sale)))
    }

    @Test fun corruptJournalAlwaysLocksNewCharges() {
        assertEquals(null to false, recoverJournal(null, false))
        assertEquals(null to true, recoverJournal(null, true))
        assertEquals(null to true, recoverJournal("invalid json", false))
        assertEquals(null to true, recoverJournal("", false))
    }

    @Test fun responseSupportsMissingStatusAndNullableTransaction() {
        val sale = readSale(JSONObject("""{"saleId":"s1","totalCents":1800,"chargedCents":1,"expiresAt":1794096000.25,"txId":null}"""))
        assertEquals("pending", sale.status)
        assertNull(sale.txId)
        assertEquals(1794096000.25, sale.expiresAt, 0.001)
    }

    @Test fun demoCashSaleUsesCatalogPricesAndChange() = runBlocking {
        val repo = DemoRepository()
        val sale = repo.create(2, listOf(CartLine(1, 2000)), PAYMENT_CASH, 5000, null)
        assertEquals("paid_cash", sale.status)
        assertEquals(3600L, sale.totalCents)
        assertEquals(1400L, sale.changeCents)
        assertTrue(sale.qrImage.isBlank())
        assertEquals(22000, repo.bootstrap().products.first { it.id == 1 }.stockMilli)
        val report = repo.report()
        assertEquals(3600L, report.totalCents)
        assertEquals(3600L, report.collectedCents)
        assertEquals(3600L, report.cashCents)
        assertEquals(1, report.salesCount)
    }

    @Test fun demoCreditChargesCustomerAndAbonoReducesBalance() = runBlocking {
        val repo = DemoRepository()
        val before = repo.customer(1).customer.balanceCents
        val sale = repo.create(2, listOf(CartLine(1, 1000)), PAYMENT_FIADO, null, 1)
        assertEquals("credit", sale.status)
        assertEquals(before + 1800, repo.customer(1).customer.balanceCents)
        assertEquals(1800L, repo.report().fiadoCents)
        val balance = repo.abono(1, 300, 2, "abono")
        assertEquals(before + 1500, balance)
        assertEquals(1, repo.customer(1).entries.count { it.kind == "payment" })
    }

    @Test fun demoInventoryAdjustsOneUnit() = runBlocking {
        val repo = DemoRepository()
        val before = repo.bootstrap().products.first { it.id == 1 }.stockMilli
        val updated = repo.adjust(2, 1, 1000, "conteo")
        assertEquals(before + 1000, updated.stockMilli)
        assertEquals(before + 1000, repo.bootstrap().products.first { it.id == 1 }.stockMilli)
        val down = repo.adjust(2, 1, -1000, "conteo")
        assertEquals(before, down.stockMilli)
    }

    @Test fun demoPeyConfirmationIsIdempotent() = runBlocking {
        val repo = DemoRepository()
        val sale = repo.create(2, listOf(CartLine(1, 1000)), PAYMENT_PEY, null, null)
        assertEquals("pending", sale.status)
        assertEquals(1L, sale.chargedCents)
        assertEquals(1, repo.report().pending)
        repo.simulatePaid(sale)
        repo.simulatePaid(sale)
        assertEquals("paid_pey", repo.status(sale.id).status)
        assertEquals(1, repo.report().salesCount)
        assertEquals(1800L, repo.report().peyCents)
        assertEquals(0, repo.report().pending)
    }

    @Test fun demoBarcodeLinkEnablesUnknownCode() = runBlocking {
        val repo = DemoRepository()
        assertEquals(1, repo.lookup("7500000000001").id)
        assertTrue(runCatching { repo.lookup("7509999999999") }.exceptionOrNull() is ApiFailure)
        repo.link("7509999999999", 3)
        assertEquals(3, repo.lookup("7509999999999").id)
    }

    @Test fun demoParserUnderstandsTextAndVoicePhrases() = runBlocking {
        val repo = DemoRepository()
        val result = repo.parse("dos cocas y medio kilo de tortillas")
        assertEquals(2, result.items.size)
        assertEquals(2000, result.items.first { it.productId == 1 }.qtyMilli)
        assertEquals(500, result.items.first { it.productId == 9 }.qtyMilli)
    }
}
