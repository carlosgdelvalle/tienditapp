package mx.abarpay.mobile

import kotlinx.coroutines.runBlocking
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

/** Contrato v3 · repositorio: catálogo, plantillas, tareas, gastos y demo grande. */
class V3RepositoryTest {
    private fun repo(server: MockWebServer) = ApiRepository(server.url("/").toString().trimEnd('/'))

    // ------------------------------------------------------------------
    // API
    // ------------------------------------------------------------------

    @Test fun catalogQueryUsesContractParamsAndReadsV3Fields() = runBlocking {
        val server = MockWebServer()
        server.start()
        try {
            server.enqueue(MockResponse().setBody("""{"items":[{"id":7,"name":"Corte de cabello","unit":"servicio","priceCents":12000,"stockMilli":0,"unlimitedStock":true,"kind":"servicio","category":"Estética","durationMinutes":30,"aliases":["corte","cabello"],"quick":true}],"total":42}"""))
            val page = repo(server).catalog(query = "corte de cabello", category = "Estética", kind = "servicio", limit = 10, offset = 5)
            assertEquals(42, page.total)
            val item = page.items.single()
            assertEquals(KIND_SERVICIO, item.kind)
            assertEquals("Estética", item.category)
            assertEquals(30, item.durationMinutes)
            assertEquals(listOf("corte", "cabello"), item.aliases)
            assertTrue(item.quick)
            val request = server.takeRequest()
            assertEquals("GET", request.method)
            assertTrue(request.path!!.startsWith("/api/catalog?"))
            assertTrue(request.path!!.contains("q=corte+de+cabello") || request.path!!.contains("q=corte%20de%20cabello"))
            assertTrue(request.path!!.contains("category=Est%C3%A9tica"))
            assertTrue(request.path!!.contains("kind=servicio"))
            assertTrue(request.path!!.contains("limit=10"))
            assertTrue(request.path!!.contains("offset=5"))
        } finally { server.shutdown() }
    }

    @Test fun catalogCreateUpdateDeleteUseOwnerEndpoints() = runBlocking {
        val server = MockWebServer()
        server.start()
        try {
            val created = """{"id":61,"name":"Corte express","unit":"servicio","priceCents":8000,"stockMilli":0,"unlimitedStock":true,"kind":"servicio","category":"Estética","durationMinutes":20,"aliases":["rapido"],"quick":true}"""
            server.enqueue(MockResponse().setBody(created))
            server.enqueue(MockResponse().setBody(created.replace("Corte express", "Corte express 2")))
            server.enqueue(MockResponse().setResponseCode(409).setBody("""{"detail":"No se puede borrar: tiene ventas o movimientos"}"""))
            val repo = repo(server)
            repo.actAs(1)
            val draft = CatalogDraft(
                name = "Corte express", unit = "servicio", priceCents = 8000,
                aliases = listOf("rapido"), unlimitedStock = true, kind = KIND_SERVICIO,
                category = "Estética", durationMinutes = 20, quick = true,
            )
            assertEquals(61, repo.createCatalogItem(draft).id)
            val post = server.takeRequest()
            assertEquals("POST", post.method)
            assertEquals("/api/catalog", post.path)
            assertEquals("1", post.getHeader("X-Employee-Id"))
            val postBody = JSONObject(post.body.readUtf8())
            assertEquals(
                setOf("name", "unit", "priceCents", "aliases", "stockMilli", "unlimitedStock", "kind", "category", "durationMinutes", "quick"),
                postBody.keys().asSequence().toSet(),
            )
            assertEquals("servicio", postBody.getString("unit"))
            assertEquals(KIND_SERVICIO, postBody.getString("kind"))
            assertEquals("Estética", postBody.getString("category"))
            assertEquals(20, postBody.getInt("durationMinutes"))
            assertEquals(1, postBody.getJSONArray("aliases").length())
            assertTrue(postBody.getBoolean("unlimitedStock"))
            assertEquals("Corte express 2", repo.updateCatalogItem(61, draft.copy(name = "Corte express 2")).name)
            val patch = server.takeRequest()
            assertEquals("PATCH", patch.method)
            assertEquals("/api/catalog/61", patch.path)
            assertEquals("Corte express 2", JSONObject(patch.body.readUtf8()).getString("name"))
            val error = runCatching { repo.deleteCatalogItem(61) }.exceptionOrNull()
            assertTrue(error is ApiFailure)
            assertEquals(409, (error as ApiFailure).code)
            val delete = server.takeRequest()
            assertEquals("DELETE", delete.method)
            assertEquals("/api/catalog/61", delete.path)
        } finally { server.shutdown() }
    }

    @Test fun templateApplyPostsBusinessTypeAndReports409() = runBlocking {
        val server = MockWebServer()
        server.start()
        try {
            server.enqueue(MockResponse().setBody("""{"ok":true,"items":24,"tasks":4}"""))
            server.enqueue(MockResponse().setResponseCode(409).setBody("""{"detail":"La tienda ya tiene catálogo"}"""))
            val repo = repo(server)
            repo.actAs(1)
            repo.applyTemplate("taqueria")
            val request = server.takeRequest()
            assertEquals("POST", request.method)
            assertEquals("/api/catalog/templates/apply", request.path)
            assertEquals(
                setOf("businessType"),
                JSONObject(request.body.readUtf8()).keys().asSequence().toSet(),
            )
            val error = runCatching { repo.applyTemplate("tiendita") }.exceptionOrNull()
            assertTrue(error is ApiFailure)
            assertEquals(409, (error as ApiFailure).code)
        } finally { server.shutdown() }
    }

    @Test fun tasksReadAndPatchAssignment() = runBlocking {
        val server = MockWebServer()
        server.start()
        try {
            server.enqueue(MockResponse().setBody("""{"items":[{"id":1,"key":"inventario","title":"Contar inventario","assignedEmployeeId":2,"active":true},{"id":2,"key":"limpieza","title":"Limpiar tienda","assignedEmployeeId":null,"active":true}]}"""))
            server.enqueue(MockResponse().setBody("""{"id":2,"key":"limpieza","title":"Limpiar tienda","assignedEmployeeId":2,"active":true}"""))
            server.enqueue(MockResponse().setBody("""{"id":2,"key":"limpieza","title":"Limpiar tienda","assignedEmployeeId":null,"active":false}"""))
            val repo = repo(server)
            repo.actAs(2)
            val tasks = repo.tasks()
            assertEquals(2, tasks.size)
            assertEquals(2, tasks[0].assignedEmployeeId)
            assertNull(tasks[1].assignedEmployeeId)
            val get = server.takeRequest()
            assertEquals("/api/tasks", get.path)
            assertEquals("2", get.getHeader("X-Employee-Id"))
            val assigned = repo.patchTask(2, assignedEmployeeId = 2, active = true)
            assertEquals(2, assigned.assignedEmployeeId)
            val patch = server.takeRequest()
            assertEquals("PATCH", patch.method)
            assertEquals("/api/tasks/2", patch.path)
            val patchBody = JSONObject(patch.body.readUtf8())
            assertEquals(2, patchBody.getInt("assignedEmployeeId"))
            assertEquals(true, patchBody.getBoolean("active"))
            val cleared = repo.patchTask(2, clearAssignee = true, active = false)
            assertNull(cleared.assignedEmployeeId)
            val clearBody = JSONObject(server.takeRequest().body.readUtf8())
            assertTrue(clearBody.isNull("assignedEmployeeId"))
            assertEquals(false, clearBody.getBoolean("active"))
        } finally { server.shutdown() }
    }

    @Test fun expensesUseContractBodiesAndVoiceDoesNotSave() = runBlocking {
        val server = MockWebServer()
        server.start()
        try {
            server.enqueue(MockResponse().setBody("""{"id":9,"amountCents":2000,"note":"gas","createdAt":1700000000.0,"employeeName":"Lupita · Lupis"}"""))
            server.enqueue(MockResponse().setBody("""{"items":[{"id":9,"amountCents":2000,"note":"gas","createdAt":1700000000.0}]}"""))
            server.enqueue(MockResponse().setBody("""{"amountCents":2000,"note":"gas"}"""))
            server.enqueue(MockResponse().setBody("""{"amountCents":null,"note":"No entendí el monto"}"""))
            val repo = repo(server)
            repo.actAs(2)
            val expense = repo.addExpense(2000, "gas")
            assertEquals(2000L, expense.amountCents)
            assertEquals("Lupita · Lupis", expense.employeeName)
            val post = server.takeRequest()
            assertEquals("/api/expenses", post.path)
            val body = JSONObject(post.body.readUtf8())
            assertEquals(setOf("amountCents", "note"), body.keys().asSequence().toSet())
            assertEquals(2000L, body.getLong("amountCents"))
            assertEquals(1, repo.expenses(50).size)
            val list = server.takeRequest()
            assertEquals("/api/expenses?limit=50", list.path)
            assertEquals(ExpenseDraft(2000, "gas"), repo.expenseVoice("veinte pesos de gas"))
            val voice = server.takeRequest()
            assertEquals("/api/expenses/voice", voice.path)
            assertEquals("veinte pesos de gas", JSONObject(voice.body.readUtf8()).getString("text"))
            assertEquals(0L, repo.expenseVoice("no se").amountCents)
        } finally { server.shutdown() }
    }

    @Test fun reportReadsExpensesOfTheDay() = runBlocking {
        val server = MockWebServer()
        server.start()
        try {
            server.enqueue(MockResponse().setBody("""{"totalCents":5000,"collectedCents":3200,"totalExpensesCents":1250,"salesCount":3}"""))
            val report = repo(server).report()
            assertEquals(1250L, report.totalExpensesCents)
            assertEquals("/api/reports/today", server.takeRequest().path)
        } finally { server.shutdown() }
    }

    // ------------------------------------------------------------------
    // Demo (simulación sin red)
    // ------------------------------------------------------------------

    @Test fun demoCatalogIsLargeWithCategoriesAndSearch() = runBlocking {
        val demo = DemoRepository()
        val page = demo.catalog(limit = 500)
        assertTrue("El demo debe simular un catálogo grande", page.items.size >= 55)
        assertTrue(page.total >= 55)
        assertTrue(page.items.count { it.category != null } >= 50)
        assertTrue(page.items.any { it.kind == KIND_SERVICIO })
        assertTrue(page.items.any { it.kind == KIND_PLATILLO })
        val bebidas = demo.catalog(category = "Bebidas", limit = 500)
        assertTrue(bebidas.items.isNotEmpty())
        assertTrue(bebidas.items.all { it.category == "Bebidas" })
        val busqueda = demo.catalog(query = "coca", limit = 500)
        assertTrue(busqueda.items.any { it.name == "Coca-Cola 600 ml" })
        val pageada = demo.catalog(limit = 10, offset = 10)
        assertEquals(10, pageada.items.size)
        assertEquals(page.total, pageada.total)
    }

    @Test fun demoCatalogCrudControlsStockAndBlocksDeleteWith409() = runBlocking {
        val demo = DemoRepository()
        demo.actAs(1)
        val service = demo.createCatalogItem(
            CatalogDraft(name = "Corte express", unit = "servicio", priceCents = 8000, kind = KIND_SERVICIO, durationMinutes = 20),
        )
        assertTrue(service.unlimitedStock)
        assertFalse(service.tracksStock)
        assertEquals(0, service.stockMilli)
        val updated = demo.updateCatalogItem(service.id, catalogDraft(service).copy(name = "Corte express 2", priceCents = 9000))
        assertEquals("Corte express 2", updated.name)
        assertEquals(9000L, updated.priceCents)
        assertTrue(demo.catalog(query = "express").items.any { it.name == "Corte express 2" })
        demo.deleteCatalogItem(service.id)
        assertTrue(demo.catalog(query = "express").items.isEmpty())
        // Con ventas encima, el servidor (y el demo) responden 409.
        demo.create(2, listOf(CartLine(1, 1000)), PAYMENT_CASH, 5000, null)
        val error = runCatching { demo.deleteCatalogItem(1) }.exceptionOrNull()
        assertTrue(error is ApiFailure)
        assertEquals(409, (error as ApiFailure).code)
        // Empleado sin permiso de dueño no edita el catálogo.
        demo.actAs(2)
        assertTrue(runCatching { demo.createCatalogItem(CatalogDraft(name = "X", priceCents = 100)) }.exceptionOrNull() is ApiFailure)
    }

    @Test fun demoTemplatesReproduceCatalogAndTasksByBusinessType() = runBlocking {
        val demo = DemoRepository()
        demo.actAs(1)
        demo.applyTemplate("taqueria")
        val taqueria = demo.catalog(limit = 500)
        assertTrue(taqueria.items.any { it.name.contains("Taco") })
        assertTrue(taqueria.items.all { it.kind == KIND_PLATILLO || it.name.contains("Refresco") })
        val taqueriaTasks = demo.tasks()
        assertTrue(taqueriaTasks.isNotEmpty())
        assertTrue(taqueriaTasks.all { it.assignedEmployeeId == null })

        demo.applyTemplate("Peluquería/Barbería")
        val peluqueria = demo.catalog(limit = 500)
        assertTrue(peluqueria.items.any { it.unit == "servicio" })
        assertTrue(peluqueria.items.filter { it.unit == "servicio" }.all { it.durationMinutes != null })

        // Miscelánea no tiene plantilla propia: usa la genérica («otro»).
        demo.applyTemplate("Miscelánea")
        assertTrue(demo.catalog(limit = 500).items.any { it.name == "Producto de ejemplo" })
    }

    @Test fun demoTasksFilterByEmployeeAndAllowAssignment() = runBlocking {
        val demo = DemoRepository()
        demo.actAs(1)
        val all = demo.tasks()
        assertTrue(all.size >= 4)
        assertTrue(all.any { it.assignedEmployeeId == null })
        // Lupita (2): solo sus tareas asignadas y activas; no ve las sin asignar.
        demo.actAs(2)
        val mine = demo.tasks()
        assertEquals(listOf(1), mine.map { it.id })
        assertTrue(mine.none { it.assignedEmployeeId == null })
        // Toño (3) ve la suya.
        demo.actAs(3)
        assertEquals(listOf(3), demo.tasks().map { it.id })
        // El dueño asigna la tarea sin asignar a Toño y la desactiva.
        demo.actAs(1)
        val assigned = demo.patchTask(2, assignedEmployeeId = 3)
        assertEquals(3, assigned.assignedEmployeeId)
        demo.actAs(3)
        assertTrue(demo.tasks().any { it.id == 2 })
        demo.actAs(1)
        demo.patchTask(2, active = false)
        demo.actAs(3)
        assertFalse(demo.tasks().any { it.id == 2 })
        demo.actAs(1)
        val cleared = demo.patchTask(2, clearAssignee = true, active = true)
        assertNull(cleared.assignedEmployeeId)
    }

    @Test fun demoExpensesFeedTheReportOfTheDay() = runBlocking {
        val demo = DemoRepository()
        demo.actAs(2)
        val expense = demo.addExpense(2000, "gas")
        assertEquals(2000L, expense.amountCents)
        assertEquals("gas", expense.note)
        demo.actAs(1)
        assertEquals(2000L, demo.report().totalExpensesCents)
        assertEquals(1, demo.expenses().size)
        // El dictado del demo no guarda: solo propone monto y nota.
        assertEquals(ExpenseDraft(2000, "gas"), demo.expenseVoice("veinte pesos de gas"))
        assertEquals(0L, demo.expenseVoice("no se entendió").amountCents)
        val second = demo.addExpense(5000, null)
        assertNull(second.note)
        assertEquals(7000L, demo.report().totalExpensesCents)
        // GET de gastos es solo dueño.
        demo.actAs(3)
        assertTrue(runCatching { demo.expenses() }.exceptionOrNull() is ApiFailure)
    }
}
