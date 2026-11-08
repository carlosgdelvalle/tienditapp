package mx.abarpay.mobile

import kotlinx.coroutines.runBlocking
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.SocketPolicy
import java.util.concurrent.TimeUnit

class RepositoryTest {
    @Test fun corruptJournalAlwaysLocksNewCharges() {
        assertEquals(null to false, recoverJournal(null, false))
        assertEquals(null to true, recoverJournal(null, true))
        assertEquals(null to true, recoverJournal("invalid json", false))
        assertEquals(null to true, recoverJournal("", false))
    }
    @Test fun postIsNotRetriedAfterServerReceivesItAndDisconnects() = runBlocking {
        val server = MockWebServer()
        server.start()
        try {
            server.enqueue(MockResponse().setSocketPolicy(SocketPolicy.DISCONNECT_AFTER_REQUEST))
            val repo = ApiRepository(server.url("/").toString().trimEnd('/'))
            assertTrue(runCatching { repo.create(1, listOf(CartLine(1, 1))) }.isFailure)
            assertEquals(1, server.requestCount)
            val request = server.takeRequest(1, TimeUnit.SECONDS)!!
            assertEquals("POST", request.method)
            assertEquals("/api/sales", request.path)
        } finally { server.shutdown() }
    }
    @Test fun postIsNotReplayedForImmediateServiceRetry() = runBlocking {
        val server = MockWebServer()
        server.start()
        try {
            server.enqueue(MockResponse().setResponseCode(503).addHeader("Retry-After", "0"))
            server.enqueue(MockResponse().setResponseCode(503))
            val repo = ApiRepository(server.url("/").toString().trimEnd('/'))
            assertTrue(runCatching { repo.create(1, listOf(CartLine(1, 1))) }.exceptionOrNull() is ApiFailure)
            assertEquals(1, server.requestCount)
        } finally { server.shutdown() }
    }
    @Test fun postRedirectIsNotFollowed() = runBlocking {
        val server = MockWebServer()
        server.start()
        try {
            server.enqueue(MockResponse().setResponseCode(307).addHeader("Location", server.url("/again")))
            val repo = ApiRepository(server.url("/").toString().trimEnd('/'))
            assertTrue(runCatching { repo.create(1, listOf(CartLine(1, 1))) }.exceptionOrNull() is ApiFailure)
            assertEquals(1, server.requestCount)
        } finally { server.shutdown() }
    }
    @Test fun salePayloadNeverSendsPriceOrPaymentState() {
        val j = saleRequest(2, listOf(CartLine(4, 3)))
        assertEquals(setOf("employeeId", "items"), j.keys().asSequence().toSet())
        val line = j.getJSONArray("items").getJSONObject(0)
        assertEquals(setOf("productId", "qty"), line.keys().asSequence().toSet())
        assertEquals(3, line.getInt("qty"))
    }
    @Test fun responseSupportsMissingStatusAndNullableTransaction() {
        val sale = readSale(JSONObject("""{"saleId":"s1","totalCents":1800,"chargedCents":1,"expiresAt":1794096000.25,"txId":null}"""))
        assertEquals("pending", sale.status)
        assertNull(sale.txId)
        assertEquals(1794096000.25, sale.expiresAt, 0.001)
    }
    @Test fun journalRoundTripRetainsQrAndChargedAmount() {
        val sale = Sale("s1", 1800, 1, "data:image/png;base64,AA==", 1200.5, "expired", note = "cancelada")
        assertEquals(sale, readSale(saleJson(sale)))
    }
    @Test fun simulatedPaymentUpdatesInventoryAndReportsOnce() = runBlocking {
        val repo = DemoRepository()
        val initial = repo.bootstrap().products.first().stock
        val sale = repo.create(1, listOf(CartLine(1, 2)))
        assertFalse(repo.status(sale).paid)
        assertTrue(sale.qrImage.isBlank())
        repo.simulatePaid(sale)
        repo.simulatePaid(sale)
        assertTrue(repo.status(sale).paid)
        assertEquals(initial - 2, repo.bootstrap().products.first().stock)
        assertEquals(1, repo.report().salesCount)
        assertEquals(3600L, repo.report().totalCents)
        assertEquals(1L, repo.report().chargedCents)
    }
    @Test fun simulatedCodesAreExplicitlyFictional() = runBlocking {
        val repo = DemoRepository()
        assertEquals(1, repo.lookup("DEMO-1"))
        assertTrue(runCatching { repo.lookup("7501234567890") }.isFailure)
    }
}
