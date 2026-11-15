package mx.abarpay.mobile

import kotlinx.coroutines.runBlocking
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** Contrato v3.2 · historial de fiado en API y simulación, con el gate de canFiado. */
class FiadoEntriesRepositoryTest {
    @Test fun apiHistorySendsIdentityAndReadsEntries() = runBlocking {
        val server = MockWebServer()
        server.start()
        try {
            server.enqueue(MockResponse().setBody(
                """{"items":[
                   {"id":3,"kind":"payment","amountCents":500,"note":"abono","employeeName":"Lupita","createdAt":1763238000.0},
                   {"id":1,"kind":"charge","amountCents":1800,"note":null,"employeeName":"Lupita","createdAt":1763234400.0}
                ]}""",
            ))
            val repo = ApiRepository(server.url("/").toString().trimEnd('/'))
            repo.actAs(2)
            val entries = repo.fiadoEntries(7)
            assertEquals(listOf("payment", "charge"), entries.map { it.kind })
            assertEquals(500L, entries[0].amountCents)
            assertEquals("abono", entries[0].note)
            assertEquals("Lupita", entries[0].employeeName)
            assertNull(entries[1].note)
            val request = server.takeRequest()
            assertEquals("GET", request.method)
            assertEquals("/api/fiado/customers/7/entries", request.path)
            assertEquals("2", request.getHeader("X-Employee-Id"))
        } finally {
            server.shutdown()
        }
    }

    @Test fun apiHistoryPropagatesPermissionFailure() = runBlocking {
        val server = MockWebServer()
        server.start()
        try {
            server.enqueue(
                MockResponse().setResponseCode(403)
                    .setBody("""{"detail":"Tu perfil no puede registrar abonos"}"""),
            )
            val repo = ApiRepository(server.url("/").toString().trimEnd('/'))
            repo.actAs(5)
            val error = runCatching { repo.fiadoEntries(1) }.exceptionOrNull()
            assertTrue(error is ApiFailure)
            assertEquals(403, (error as ApiFailure).code)
            assertEquals("Tu perfil no puede registrar abonos", error.message)
        } finally {
            server.shutdown()
        }
    }

    @Test fun demoSeedsChargesAndPaymentsForEachCustomer() = runBlocking {
        val repo = DemoRepository()
        repo.actAs(2)
        val customers = repo.customers()
        assertTrue(customers.isNotEmpty())
        customers.forEach { customer ->
            val history = repo.fiadoEntries(customer.id)
            assertTrue("sin historial para " + customer.name, history.isNotEmpty())
            val balance = history.sumOf {
                if (it.kind == "payment") -it.amountCents else it.amountCents
            }
            assertEquals(customer.balanceCents, balance)
            assertTrue(history.zipWithNext().all { (a, b) -> a.createdAt >= b.createdAt })
            assertTrue(history.all { !it.employeeName.isNullOrBlank() })
        }
        assertTrue(repo.fiadoEntries(2).any { it.kind == "payment" })
    }

    @Test fun demoAbonoAddsPaymentEntryWithEmployeeName() = runBlocking {
        val repo = DemoRepository()
        repo.actAs(2) // Lupita, canFiado
        val before = repo.customer(1).customer.balanceCents
        val count = repo.fiadoEntries(1).size
        val balance = repo.abono(1, 500, 2, "abono prueba")
        assertEquals(before - 500, balance)
        val history = repo.fiadoEntries(1)
        assertEquals(count + 1, history.size)
        assertEquals("payment", history.first().kind)
        assertEquals(500L, history.first().amountCents)
        assertEquals("abono prueba", history.first().note)
        assertEquals("Lupita", history.first().employeeName)
        assertEquals(balance, repo.customer(1).customer.balanceCents)
    }

    @Test fun demoEmployeeWithoutFiadoCannotAbonoNorReadNamedHistory() = runBlocking {
        val repo = DemoRepository()
        repo.actAs(5) // Beto, sin canFiado
        val deniedAbono = runCatching { repo.abono(1, 100, 5, null) }.exceptionOrNull()
        assertTrue(deniedAbono is ApiFailure)
        assertEquals(403, (deniedAbono as ApiFailure).code)
        assertEquals("Tu perfil no puede registrar abonos", deniedAbono.message)
        val deniedHistory = runCatching { repo.fiadoEntries(1) }.exceptionOrNull()
        assertTrue(deniedHistory is ApiFailure)
        assertEquals(403, (deniedHistory as ApiFailure).code)
        // El detalle del cliente sigue disponible: saldo e historial visibles.
        val detail = repo.customer(1)
        assertEquals(3_500L, detail.customer.balanceCents)
        assertTrue(detail.entries.isNotEmpty())
    }
}
