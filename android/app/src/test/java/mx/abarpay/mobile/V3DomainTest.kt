package mx.abarpay.mobile

import org.junit.Assert.*
import org.junit.Test

/** Contrato v3 · dominio: tipos de negocio, catálogo, presets, tareas, gastos y comprobante. */
class V3DomainTest {
    @Test fun businessTypesMapToServerTemplates() {
        assertEquals(9, BUSINESS_TYPES.size)
        assertEquals("tiendita", templateBusinessType("Tiendita/Abarrotes"))
        assertEquals("tortilleria", templateBusinessType("Tortillería"))
        assertEquals("taqueria", templateBusinessType("Taquería"))
        assertEquals("comida-corrida", templateBusinessType("Comida corrida"))
        assertEquals("peluqueria", templateBusinessType("Peluquería/Barbería"))
        assertEquals("estetica", templateBusinessType("Estética de uñas"))
        assertEquals("fondita", templateBusinessType("Fondita"))
        // Miscelánea no existe en el enum del servidor: usa la plantilla genérica.
        assertEquals("otro", templateBusinessType("Miscelánea"))
        assertEquals("otro", templateBusinessType("Otro"))
        assertEquals("otro", templateBusinessType("tipo desconocido"))
    }

    @Test fun sellsStepHasThreeOptions() {
        assertEquals(
            listOf("Productos", "Servicios", "Comida preparada y bebidas"),
            SELLS_OPTIONS.map { it.label },
        )
    }

    @Test fun kindsAndUnitsFollowTheContract() {
        assertEquals(listOf("producto", "servicio", "platillo"), PRODUCT_KINDS)
        assertTrue(PRODUCT_UNITS.containsAll(listOf("pieza", "kg", "g", "litro", "servicio", "sesion", "turno", "minuto", "hora", "paquete", "combo")))
        assertTrue(kindTracksStock(KIND_PRODUCTO))
        assertFalse(kindTracksStock(KIND_SERVICIO))
        assertFalse(kindTracksStock(KIND_PLATILLO))
        assertEquals("Servicio", kindLabel(KIND_SERVICIO))
        assertEquals("Platillo", kindLabel(KIND_PLATILLO))
        assertEquals("Producto", kindLabel(KIND_PRODUCTO))
    }

    @Test fun quantityPresetsByUnit() {
        listOf("servicio", "sesion", "turno", "combo").forEach {
            assertEquals(it, listOf(1000, 2000, 3000), quantityPresets(it))
        }
        assertEquals(listOf(250, 500, 1000, 2000), quantityPresets("kg"))
        assertEquals(listOf(30_000, 60_000, 90_000), quantityPresets("minuto"))
        listOf("pieza", "g", "paquete", "litro", "hora").forEach { assertNull(it, quantityPresets(it)) }
        assertEquals(1000, quantityStep("g"))
        assertEquals(1000, quantityStep("pieza"))
        assertEquals(1000, quantityStep("paquete"))
        assertEquals("250 g", quantityPresetLabel(250, "kg"))
        assertEquals("30 min", quantityPresetLabel(30_000, "minuto"))
        assertEquals("2 servicio", quantityPresetLabel(2000, "servicio"))
        assertEquals("1 sesión", quantityPresetLabel(1000, "sesion"))
        assertEquals("-2 pza", quantityPresetLabel(-2000, "pieza"))
    }

    @Test fun quantityTextUnderstandsNewUnits() {
        assertEquals("250 g", qtyText(250_000, "g"))
        assertEquals("0.25 g", qtyText(250, "g"))
        assertEquals("2 servicio", qtyText(2000, "servicio"))
        assertEquals("1 sesión", qtyText(1000, "sesion"))
        assertEquals("30 min", qtyText(30_000, "minuto"))
        assertEquals("1 L", qtyText(1000, "litro"))
        assertEquals("1 combo", qtyText(1000, "combo"))
        assertEquals("2 kg", qtyText(2000, "kg"))
    }

    @Test fun stockBadgesUseDisponiblesAndInventarioBajo() {
        assertEquals("Tu negocio", COPY_HOME_TITLE)
        assertEquals("Inventario bajo", COPY_LOW_STOCK)
        val product = Product(1, "Coca-Cola", "pieza", 1800, 24000)
        assertEquals("24 unidades disponibles", product.availableLabel)
        assertEquals("24 unidades disponibles", stockBadge(product))
        assertTrue(product.tracksStock)
        val service = Product(2, "Corte", "servicio", 12000, 0, kind = KIND_SERVICIO, unlimitedStock = true)
        assertEquals("Sin límite", service.availableLabel)
        assertFalse(service.tracksStock)
    }

    @Test fun catalogDraftRoundTripsAndValidates() {
        val product = Product(
            7, "Corte de cabello", "servicio", 12000, 0,
            kind = KIND_SERVICIO, category = "Estética", durationMinutes = 30,
            unlimitedStock = true, aliases = listOf("corte"), quick = true,
        )
        val draft = catalogDraft(product)
        assertEquals("Corte de cabello", draft.name)
        assertEquals(12000L, draft.priceCents)
        assertEquals(KIND_SERVICIO, draft.kind)
        assertEquals("Estética", draft.category)
        assertEquals(30, draft.durationMinutes)
        assertTrue(draft.unlimitedStock)
        assertFalse(draft.tracksStock)
        assertTrue(catalogDraftReady(draft))
        assertFalse(catalogDraftReady(draft.copy(name = " ")))
        assertFalse(catalogDraftReady(draft.copy(priceCents = 0)))
        assertEquals(listOf("coca", "refresco"), aliasesFrom(" coca , refresco, , coca "))
        assertEquals("coca, refresco", aliasesText(listOf("coca", "refresco")))
    }

    @Test fun catalogSearchMatchesNameAndAliases() {
        val coca = Product(1, "Coca-Cola 600 ml", "pieza", 1800, 24000, category = "Bebidas", aliases = listOf("coca", "refresco"))
        val pan = Product(2, "Pan Bimbo", "pieza", 4800, 6000, category = "Panadería")
        assertTrue(catalogMatches(coca, "coca", null, null))
        assertTrue(catalogMatches(coca, "REFRESCO", null, null))
        assertFalse(catalogMatches(coca, "pan", null, null))
        assertFalse(catalogMatches(coca, "", "Panadería", null))
        assertTrue(catalogMatches(pan, "", null, KIND_PRODUCTO))
        assertFalse(catalogMatches(pan, "", null, KIND_SERVICIO))
        assertEquals(listOf("Bebidas", "Panadería"), catalogCategories(listOf(coca, pan)))
        assertEquals(listOf(1, 2), sortedCatalog(listOf(coca, pan)).map { it.id })
        val quick = coca.copy(quick = true)
        assertEquals(listOf(1, 2), sortedCatalog(listOf(pan, quick)).map { it.id })
    }

    @Test fun tasksOnlyShowAssignedAndActiveToEmployees() {
        val tasks = listOf(
            DayTask(1, "inventario", "Contar inventario", assignedEmployeeId = 2, active = true),
            DayTask(2, "limpieza", "Limpiar tienda", assignedEmployeeId = null, active = true),
            DayTask(3, "caducidad", "Revisar caducidad", assignedEmployeeId = 3, active = true),
            DayTask(4, "anaquel", "Acomodar anaquel", assignedEmployeeId = 2, active = false),
        )
        val lupita = Employee(2, "Lupita", "employee", nickname = "Lupis")
        assertEquals(listOf(1), tasksFor(tasks, lupita).map { it.id })
        assertEquals(listOf(3), tasksFor(tasks, Employee(3, "Toño", "employee")).map { it.id })
        assertEquals(4, tasksFor(tasks, Employee(1, "Doña Rosa", "owner")).size)
        assertEquals(4, tasksFor(tasks, null).size)
        val team = listOf(Employee(1, "Doña Rosa", "owner"), lupita, Employee(3, "Toño", "employee"))
        assertEquals("Lupita · Lupis", taskAssigneeName(tasks[0], team))
        assertEquals("Sin asignar", taskAssigneeName(tasks[1], team))
        assertEquals(listOf(2, 3), assignableEmployees(team).map { it.id })
    }

    @Test fun expenseVoiceParsesWordsAndDigits() {
        assertEquals(ExpenseDraft(2000, "gas"), parseExpenseVoice("veinte pesos de gas"))
        assertEquals(ExpenseDraft(15000, "gasolina"), parseExpenseVoice("150 de gasolina"))
        assertEquals(ExpenseDraft(5000, "luz"), parseExpenseVoice("50 pesos de luz"))
        assertEquals(ExpenseDraft(10000, "agua"), parseExpenseVoice("cien pesos de agua"))
        assertNull(parseExpenseVoice(""))
        assertNull(parseExpenseVoice("gasté en el mercado"))
        assertTrue(expenseReady(2000))
        assertFalse(expenseReady(0))
        assertFalse(expenseReady(null))
        assertEquals("Entendí: $20.00 · gas", expenseVoiceMessage(ExpenseDraft(2000, "gas")))
        assertEquals("Gasto registrado: $20.00 · gas", expenseRegisteredMessage(2000, "gas"))
        assertEquals("Sin nota", expenseVoiceMessage(ExpenseDraft(0, "Sin nota")))
        assertEquals("20", cashInputText(2000))
        assertEquals("20.50", cashInputText(2050))
    }

    @Test fun receiptRowsSummarizeEverySettledSale() {
        val cash = Sale("s1", 3600, 3600, status = "paid_cash", paymentMethod = PAYMENT_CASH, cashReceivedCents = 5000, changeCents = 1400)
        assertTrue(canShareReceipt(cash))
        val rows = receiptRows("Mi negocio", cash)
        assertEquals("Mi negocio", rows.first { it.label == "Negocio" }.value)
        assertEquals("$36.00", rows.first { it.label == "Total" }.value)
        assertEquals("$50.00", rows.first { it.label == "Recibido" }.value)
        assertEquals("$14.00", rows.first { it.label == "Cambio" }.value)
        assertEquals("Comprobante de venta", receiptHeadline(cash))
        val fiado = Sale("s2", 1800, 1800, status = "credit", paymentMethod = PAYMENT_FIADO, customerName = "Doña Mari")
        assertEquals("Doña Mari", receiptRows("Mi negocio", fiado).first { it.label == "Cliente" }.value)
        val pending = Sale("s3", 1800, 1, status = "pending", paymentMethod = PAYMENT_PEY)
        assertFalse(canShareReceipt(pending))
        assertTrue(receiptRows("Mi negocio", pending).any { it.label == "Estado" })
        assertEquals("comprobante-SIMULADO_1", receiptFileName(Sale("SIMULADO 1", 100, 100)))
    }
}
