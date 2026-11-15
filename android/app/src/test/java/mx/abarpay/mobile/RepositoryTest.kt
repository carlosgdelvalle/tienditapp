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
    @Test fun simulatedCancelRestoresStockOnceAndCannotBecomePaid() = runBlocking {
        val demo = DemoRepository()
        val before = demo.bootstrap().products.first { it.id == 1 }.stockMilli
        val sale = demo.create(1, listOf(CartLine(1, 1000)), PAYMENT_PEY)
        val canceled = demo.cancel(sale.id)
        assertEquals("canceled", canceled.status)
        demo.cancel(sale.id)
        demo.simulatePaid(canceled)
        assertEquals("canceled", demo.status(sale.id).status)
        assertEquals(before, demo.bootstrap().products.first { it.id == 1 }.stockMilli)
    }

    @Test fun cancellationUsesUnpaidOnlyServerGuard() = runBlocking {
        val server = MockWebServer()
        server.start()
        try {
            server.enqueue(MockResponse().setBody("""{"id":"s1","status":"canceled","paymentMethod":"pey","totalCents":2000,"chargedCents":1}"""))
            assertEquals("canceled", repo(server).cancel("s1").status)
            val request = server.takeRequest()
            assertEquals("POST", request.method)
            assertEquals("/api/sales/s1/cancel?pendingOnly=true", request.path)
        } finally { server.shutdown() }
    }

    @Test fun failedCancellationIsNeverReportedAsCanceled() = runBlocking {
        val server = MockWebServer()
        server.start()
        try {
            server.enqueue(MockResponse().setResponseCode(409).setBody("""{"detail":"Ya pagado"}"""))
            val error = runCatching { repo(server).cancel("s1") }.exceptionOrNull()
            assertTrue(error is ApiFailure)
            assertEquals(409, (error as ApiFailure).code)
            assertEquals(1, server.requestCount)
        } finally { server.shutdown() }
    }

    @Test fun productStockFlagSupportsNewAndExistingServers() {
        val json = JSONObject("""{"id":18,"name":"Tacos de pastor","unit":"pieza","priceCents":1000,"stockMilli":0,"unlimitedStock":true}""")
        assertTrue(readProduct(json).unlimitedStock)
        json.remove("unlimitedStock")
        assertFalse(readProduct(json).unlimitedStock)
    }

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

    // ------------------------------------------------------------------
    // Contrato v2: perfil, equipo, invitaciones, inventario y X-Employee-Id
    // ------------------------------------------------------------------

    @Test fun employeeHeaderIsSentOnlyAfterSelectingProfile() = runBlocking {
        val server = MockWebServer()
        server.start()
        try {
            server.enqueue(MockResponse().setBody("""{"totalCents":0,"salesCount":0}"""))
            server.enqueue(MockResponse().setBody("""{"totalCents":0,"salesCount":0}"""))
            val repo = repo(server)
            repo.report()
            assertNull(server.takeRequest().getHeader("X-Employee-Id"))
            repo.actAs(2)
            repo.report()
            assertEquals("2", server.takeRequest().getHeader("X-Employee-Id"))
        } finally { server.shutdown() }
    }

    @Test fun storeProfileAndPhotoUseContractBodies() = runBlocking {
        val server = MockWebServer()
        server.start()
        try {
            val profile = """{"storeId":"tiendita-esquina","name":"Tiendita","businessType":"Tiendita","ownerName":"Doña Rosa"}"""
            server.enqueue(MockResponse().setBody(profile))
            server.enqueue(MockResponse().setBody(profile.replace("Tiendita\"", "La Esquina\"")))
            server.enqueue(MockResponse().setBody("""{"ok":true}"""))
            val repo = repo(server)
            assertEquals("tiendita-esquina", repo.profile().storeId)
            repo.updateProfile(name = "La Esquina", businessType = "Abarrotes", ownerName = "Rosa")
            repo.uploadPhoto("data:image/jpeg;base64,AAAA")
            val get = server.takeRequest()
            assertEquals("GET", get.method)
            assertEquals("/api/store/profile", get.path)
            val put = server.takeRequest()
            assertEquals("PUT", put.method)
            val putBody = JSONObject(put.body.readUtf8())
            assertEquals(setOf("name", "businessType", "ownerName"), putBody.keys().asSequence().toSet())
            assertEquals("La Esquina", putBody.getString("name"))
            assertEquals("Abarrotes", putBody.getString("businessType"))
            val photo = server.takeRequest()
            assertEquals("/api/store/photo", photo.path)
            assertEquals("data:image/jpeg;base64,AAAA", JSONObject(photo.body.readUtf8()).getString("dataUrl"))
        } finally { server.shutdown() }
    }

    @Test fun employeesListAndPatchRespectPermissions() = runBlocking {
        val server = MockWebServer()
        server.start()
        try {
            server.enqueue(MockResponse().setBody("""{"items":[{"id":1,"name":"Doña Rosa","role":"owner","active":true,"canSell":true,"canFiado":true,"canInventory":true},{"id":2,"name":"Lupita","nickname":"Lupis","role":"employee","active":true,"canSell":true,"canFiado":true,"canInventory":true},{"id":4,"name":"Invitada","role":"employee","active":false,"canInventory":true}]}"""))
            server.enqueue(MockResponse().setBody("""{"id":2,"name":"Lupita","nickname":"Lupis","role":"employee","active":true,"canSell":true,"canFiado":false,"canInventory":true}"""))
            val repo = repo(server)
            val team = repo.employees()
            assertEquals(3, team.size)
            assertEquals("Lupis", team[1].nickname)
            assertTrue(team[1].canInventory)
            assertFalse(team[2].active)
            assertEquals("Invitada", team[2].name)
            assertEquals("/api/employees", server.takeRequest().path)
            val patched = repo.patchEmployee(2, canFiado = false)
            assertFalse(patched.canFiado)
            val patch = server.takeRequest()
            assertEquals("PATCH", patch.method)
            assertEquals("/api/employees/2", patch.path)
            assertEquals(setOf("canFiado"), JSONObject(patch.body.readUtf8()).keys().asSequence().toSet())
        } finally { server.shutdown() }
    }

    @Test fun inviteCreationAndAcceptanceFlow() = runBlocking {
        val server = MockWebServer()
        server.start()
        try {
            server.enqueue(MockResponse().setBody("""{"token":"abc123","employeeId":5,"url":"https://abarpay-api.onrender.com/invite/abc123"}"""))
            server.enqueue(MockResponse().setBody("""{"token":"abc123","employeeId":5,"name":"Juan","storeName":"Tiendita","businessType":"Abarrotes","canSell":true,"canFiado":false,"canInventory":true}"""))
            server.enqueue(MockResponse().setBody("""{"id":5,"name":"Juan","nickname":"Juancho","role":"employee","active":true,"canSell":true,"canFiado":false,"canInventory":true}"""))
            val repo = repo(server)
            val invite = repo.createInvite("Juan", canSell = true, canFiado = false, canInventory = true)
            assertEquals("abc123", invite.token)
            assertTrue(invite.url.endsWith("/invite/abc123"))
            val create = server.takeRequest()
            assertEquals("/api/employees/invites", create.path)
            assertEquals(
                setOf("name", "canSell", "canFiado", "canInventory"),
                JSONObject(create.body.readUtf8()).keys().asSequence().toSet(),
            )
            val info = repo.inviteInfo("abc123")
            assertEquals("Juan", info.name)
            assertEquals("Tiendita", info.storeName)
            assertFalse(info.canFiado)
            assertTrue(info.canInventory)
            assertEquals("/api/employees/invites/abc123", server.takeRequest().path)
            val accepted = repo.acceptInvite("abc123", "Juancho")
            assertEquals("Juancho", accepted.nickname)
            assertTrue(accepted.active)
            assertEquals(setOf("nickname"), JSONObject(server.takeRequest().body.readUtf8()).keys().asSequence().toSet())
        } finally { server.shutdown() }
    }

    @Test fun inventorySetAndVoiceUseContractBodies() = runBlocking {
        val server = MockWebServer()
        server.start()
        try {
            server.enqueue(MockResponse().setBody("""{"id":1,"name":"Coca-Cola 600 ml","unit":"pieza","priceCents":1800,"stockMilli":12000}"""))
            server.enqueue(MockResponse().setBody("""{"items":[{"productId":1,"name":"Coca-Cola 600 ml","qtyMilli":12000,"unit":"pieza"},{"productId":2,"name":"Pan","unit":"pieza"}],"note":"Revisa el pan"}"""))
            val repo = repo(server)
            val updated = repo.inventorySet(1, 12000, "conteo por voz")
            assertEquals(12000, updated.stockMilli)
            val set = server.takeRequest()
            assertEquals("/api/inventory/set", set.path)
            val setBody = JSONObject(set.body.readUtf8())
            assertEquals(1, setBody.getInt("productId"))
            assertEquals(12000, setBody.getInt("qtyMilli"))
            assertEquals("conteo por voz", setBody.getString("note"))
            val voice = repo.inventoryVoice("12 coca colas")
            assertEquals(2, voice.items.size)
            assertEquals(12000, voice.items[0].qtyMilli)
            assertNull(voice.items[1].qtyMilli)
            assertEquals("Revisa el pan", voice.note)
            val voiceRequest = server.takeRequest()
            assertEquals("/api/inventory/voice", voiceRequest.path)
            assertEquals("12 coca colas", JSONObject(voiceRequest.body.readUtf8()).getString("text"))
        } finally { server.shutdown() }
    }

    @Test fun inventorySnapshotReadsValueAndLastUpdate() = runBlocking {
        val server = MockWebServer()
        server.start()
        try {
            server.enqueue(MockResponse().setBody("""{"items":[{"productId":1,"name":"Coca-Cola 600 ml","unit":"pieza","priceCents":1800,"stockMilli":24000,"unlimitedStock":false,"lastUpdatedAt":1700000000.0,"lastUpdatedByName":"Lupita","lastUpdatedByNickname":"Lupis"}],"totalValueCents":43200}"""))
            val snapshot = repo(server).inventory()
            assertEquals(43200L, snapshot.totalValueCents)
            val item = snapshot.items.single()
            assertEquals(24000, item.stockMilli)
            assertEquals(1700000000.0, item.lastUpdatedAt!!, 0.001)
            assertEquals("Lupita", item.lastUpdatedByName)
            assertEquals("Lupis", item.lastUpdatedByNickname)
            assertEquals("/api/inventory", server.takeRequest().path)
        } finally { server.shutdown() }
    }

    @Test fun report403IsRecognizableForEmployees() = runBlocking {
        val server = MockWebServer()
        server.start()
        try {
            server.enqueue(MockResponse().setResponseCode(403).setBody("""{"detail":"Solo el dueño ve reportes"}"""))
            val repo = repo(server)
            repo.actAs(2)
            val error = runCatching { repo.report() }.exceptionOrNull()
            assertTrue(error is ApiFailure)
            assertEquals(403, (error as ApiFailure).code)
            assertTrue(error.message!!.contains("Solo el dueño"))
        } finally { server.shutdown() }
    }

    @Test fun demoPermissionsGateReportsAndInventory() = runBlocking {
        val demo = DemoRepository()
        demo.actAs(2)
        val reportError = runCatching { demo.report() }.exceptionOrNull()
        assertTrue(reportError is ApiFailure)
        assertEquals(403, (reportError as ApiFailure).code)
        demo.actAs(5)
        val denied = runCatching { demo.inventorySet(1, 5000) }.exceptionOrNull()
        assertTrue(denied is ApiFailure)
        assertEquals(403, (denied as ApiFailure).code)
        demo.actAs(1)
        demo.inventorySet(1, 5000)
        assertEquals(5000, demo.bootstrap().products.first { it.id == 1 }.stockMilli)
    }

    @Test fun demoInviteCreatesPendingEmployeeAndAcceptsOnce() = runBlocking {
        val demo = DemoRepository()
        demo.actAs(1)
        val invite = demo.createInvite("Juan", canSell = true, canFiado = false, canInventory = true)
        assertTrue(invite.token.isNotBlank())
        assertTrue(invite.url.contains(invite.token))
        assertTrue(demo.employees().any { it.name == "Juan" && !it.active })
        val info = demo.inviteInfo(invite.token)
        assertEquals("Juan", info.name)
        assertEquals("Tiendita de la Esquina", info.storeName)
        assertFalse(info.canFiado)
        assertTrue(info.canInventory)
        val accepted = demo.acceptInvite(invite.token, "Juancho")
        assertEquals("Juancho", accepted.nickname)
        assertTrue(accepted.active)
        assertTrue(demo.bootstrap().employees.any { it.name == "Juan" })
        val reused = runCatching { demo.inviteInfo(invite.token) }.exceptionOrNull()
        assertTrue(reused is ApiFailure)
        assertEquals(410, (reused as ApiFailure).code)
        assertTrue(runCatching { demo.acceptInvite(invite.token, "Otra") }.exceptionOrNull() is ApiFailure)
    }

    @Test fun demoOnboardingProfileAndPhoto() = runBlocking {
        val demo = DemoRepository()
        val updated = demo.updateProfile(name = "La Esquina", businessType = "Abarrotes", ownerName = "Rosa")
        assertEquals("La Esquina", updated.name)
        assertEquals("La Esquina", demo.bootstrap().store.name)
        assertEquals("Abarrotes", demo.profile().businessType)
        demo.uploadPhoto("data:image/jpeg;base64,AAAA")
        assertTrue(runCatching { demo.uploadPhoto("data:text/plain;base64,AAAA") }.isFailure)
        assertTrue(runCatching { demo.uploadPhoto("data:image/jpeg;base64," + "A".repeat(5_000_001)) }.isFailure)
    }

    @Test fun demoInventorySnapshotShowsRecentMovements() = runBlocking {
        val demo = DemoRepository()
        demo.actAs(1)
        assertTrue(demo.inventory().items.none { it.lastUpdatedAt != null })
        demo.inventorySet(1, 12000)
        val item = demo.inventory().items.first { it.productId == 1 }
        assertEquals(12000, item.stockMilli)
        assertNotNull(item.lastUpdatedAt)
        assertEquals("Doña Rosa", item.lastUpdatedByName)
        assertTrue(demo.inventory().totalValueCents > 0)
    }
}
