package mx.abarpay.mobile

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody
import okio.BufferedSink
import org.json.JSONArray
import org.json.JSONObject
import java.util.UUID
import java.util.concurrent.TimeUnit

class ApiFailure(val code: Int, message: String) : Exception(message)

interface ShopRepository {
    suspend fun bootstrap(): Bootstrap
    suspend fun report(): Report
    suspend fun parse(text: String): ParseResult
    suspend fun lookup(code: String): Product
    suspend fun link(code: String, productId: Int): Product
    suspend fun create(
        employeeId: Int,
        cart: List<CartLine>,
        paymentMethod: String,
        cashReceivedCents: Long? = null,
        customerId: Int? = null,
    ): Sale
    suspend fun status(saleId: String): Sale
    suspend fun adjust(employeeId: Int, productId: Int, deltaMilli: Int, reason: String): Product
    suspend fun customers(): List<Customer>
    suspend fun addCustomer(name: String, phone: String?): Customer
    suspend fun customer(id: Int): CustomerDetail
    suspend fun abono(customerId: Int, amountCents: Long, employeeId: Int, note: String?): Long
}

// ---------------------------------------------------------------------------
// JSON helpers
// ---------------------------------------------------------------------------

internal fun JSONArray.objects(): List<JSONObject> = (0 until length()).mapNotNull { optJSONObject(it) }
internal fun JSONArray.strings(): List<String> = (0 until length()).mapNotNull { optString(it).takeIf(String::isNotBlank) }
internal fun JSONObject.nullableString(key: String): String? =
    if (!has(key) || isNull(key)) null else optString(key).takeIf { it.isNotBlank() }
internal fun JSONObject.nullableLong(key: String): Long? =
    if (!has(key) || isNull(key)) null else optLong(key)
internal fun JSONObject.nullableInt(key: String): Int? =
    if (!has(key) || isNull(key)) null else optInt(key)

internal fun readProduct(j: JSONObject) = Product(
    id = j.optInt("id"),
    name = j.optString("name"),
    unit = j.optString("unit", "pieza").ifBlank { "pieza" },
    priceCents = j.optLong("priceCents"),
    stockMilli = j.optInt("stockMilli"),
    lowStockMilli = j.optInt("lowStockMilli", 5000),
    quick = j.optBoolean("quick"),
)

internal fun readBootstrap(j: JSONObject): Bootstrap {
    val storeJson = j.optJSONObject("store")
    val store = Store(
        id = storeJson?.optString("id").orEmpty(),
        name = storeJson?.optString("name")?.takeIf { it.isNotBlank() } ?: j.optString("store"),
    )
    return Bootstrap(
        store = store,
        products = j.optJSONArray("products")?.objects()?.map(::readProduct).orEmpty(),
        employees = j.optJSONArray("employees")?.objects()?.map {
            Employee(it.optInt("id"), it.optString("name"), it.optString("role", "employee"))
        }.orEmpty(),
        demoMode = j.optBoolean("demoMode"),
        ai = j.optString("ai", "local"),
    )
}

internal fun readParse(j: JSONObject): ParseResult = ParseResult(
    items = j.optJSONArray("items")?.objects()?.map {
        val qty = it.optInt("qtyMilli")
        val unitPrice = it.optLong("unitPriceCents")
        ParseLine(
            productId = it.optInt("productId"),
            name = it.optString("name"),
            qtyMilli = qty,
            unit = it.optString("unit", "pieza").ifBlank { "pieza" },
            unitPriceCents = unitPrice,
            lineTotalCents = if (it.has("lineTotalCents")) it.optLong("lineTotalCents") else lineTotalCents(unitPrice, qty),
        )
    }.orEmpty(),
    unmatched = j.optJSONArray("unmatched")?.strings().orEmpty(),
    engine = j.optString("engine", "local"),
)

internal fun readReport(j: JSONObject) = Report(
    totalCents = j.optLong("totalCents"),
    collectedCents = j.optLong("collectedCents"),
    cashCents = j.optLong("cashCents"),
    peyCents = j.optLong("peyCents"),
    fiadoCents = j.optLong("fiadoCents"),
    salesCount = j.optInt("salesCount"),
    byEmployee = j.optJSONArray("byEmployee")?.objects()?.map {
        EmployeeTotal(it.optString("name"), it.optLong("totalCents"), it.optInt("salesCount"))
    }.orEmpty(),
    topProducts = j.optJSONArray("topProducts")?.objects()?.map {
        TopProduct(
            name = it.optString("name"),
            qtyMilli = if (it.has("qtyMilli")) it.optInt("qtyMilli") else it.optInt("qty") * 1000,
            unit = it.optString("unit", "pieza").ifBlank { "pieza" },
            productId = it.optInt("productId"),
        )
    }.orEmpty(),
    lowStock = j.optJSONArray("lowStock")?.objects()?.map {
        StockItem(
            name = it.optString("name"),
            stockMilli = if (it.has("stockMilli")) it.optInt("stockMilli") else it.optInt("stock") * 1000,
            unit = it.optString("unit", "pieza").ifBlank { "pieza" },
        )
    }.orEmpty(),
    pending = j.optInt("pending"),
    fiadoOutstandingCents = j.optLong("fiadoOutstandingCents"),
    demoMode = j.optBoolean("demoMode"),
)

internal fun readSale(j: JSONObject, fallbackTotal: Long = 0): Sale {
    val total = if (j.has("totalCents")) j.optLong("totalCents") else fallbackTotal
    val customer = j.optJSONObject("customer")
    return Sale(
        id = j.optString("saleId").ifBlank { j.optString("id") },
        totalCents = total,
        chargedCents = if (j.has("chargedCents") && !j.isNull("chargedCents")) j.optLong("chargedCents") else total,
        status = j.optString("status", "pending"),
        paymentMethod = j.optString("paymentMethod", PAYMENT_PEY).ifBlank { PAYMENT_PEY },
        cashReceivedCents = j.nullableLong("cashReceivedCents"),
        changeCents = j.nullableLong("changeCents"),
        customerId = j.nullableInt("customerId") ?: customer?.optInt("id"),
        customerName = customer?.optString("name")?.takeIf { it.isNotBlank() } ?: j.nullableString("customerName"),
        customerBalanceCents = customer?.nullableLong("balanceCents") ?: j.nullableLong("customerBalanceCents"),
        qrId = j.nullableString("qrId") ?: j.nullableString("peyQrId"),
        qrImage = j.optString("qrImage"),
        expiresAt = j.optDouble("expiresAt", 0.0),
        txId = j.nullableString("txId") ?: j.nullableString("peyTxId"),
        note = j.nullableString("note"),
        createdAt = j.optDouble("createdAt", 0.0),
    )
}

internal fun readCustomer(j: JSONObject) = Customer(
    id = j.optInt("id"),
    name = j.optString("name"),
    phone = j.nullableString("phone"),
    balanceCents = j.optLong("balanceCents"),
)

internal fun readCustomerDetail(j: JSONObject): CustomerDetail {
    val customerJson = j.optJSONObject("customer") ?: j
    val entries = j.optJSONArray("entries")?.objects()?.map {
        FiadoEntry(
            id = it.optInt("id"),
            kind = it.optString("kind", "charge"),
            amountCents = it.optLong("amountCents"),
            note = it.nullableString("note"),
            createdAt = it.optDouble("createdAt", 0.0),
            saleId = it.nullableString("saleId"),
        )
    }.orEmpty()
    return CustomerDetail(readCustomer(customerJson), entries)
}

internal fun saleJson(s: Sale) = JSONObject()
    .put("saleId", s.id)
    .put("totalCents", s.totalCents)
    .put("chargedCents", s.chargedCents)
    .put("status", s.status)
    .put("paymentMethod", s.paymentMethod)
    .put("cashReceivedCents", s.cashReceivedCents ?: JSONObject.NULL)
    .put("changeCents", s.changeCents ?: JSONObject.NULL)
    .put("customerId", s.customerId ?: JSONObject.NULL)
    .put("customerName", s.customerName ?: JSONObject.NULL)
    .put("customerBalanceCents", s.customerBalanceCents ?: JSONObject.NULL)
    .put("qrId", s.qrId ?: JSONObject.NULL)
    .put("qrImage", s.qrImage)
    .put("expiresAt", s.expiresAt)
    .put("txId", s.txId ?: JSONObject.NULL)
    .put("note", s.note ?: JSONObject.NULL)
    .put("createdAt", s.createdAt)

internal fun saleItemsJson(cart: List<CartLine>): JSONArray = JSONArray(cart.map {
    JSONObject().put("productId", it.productId).put("qtyMilli", it.qtyMilli)
})

internal fun saleRequest(
    employeeId: Int,
    cart: List<CartLine>,
    paymentMethod: String,
    cashReceivedCents: Long?,
    customerId: Int?,
) = JSONObject()
    .put("employeeId", employeeId)
    .put("items", saleItemsJson(cart))
    .put("paymentMethod", paymentMethod)
    .apply {
        if (cashReceivedCents != null) put("cashReceivedCents", cashReceivedCents)
        if (customerId != null) put("customerId", customerId)
    }

// ---------------------------------------------------------------------------
// API client for the v1 backend
// ---------------------------------------------------------------------------

/**
 * No PEY or OpenAI credentials, cookies, automatic redirects, or POST retries.
 * All money and totals are computed by the server; the app only sends ids and milli-quantities.
 */
class ApiRepository(private val base: String) : ShopRepository {
    private val client = OkHttpClient.Builder()
        .retryOnConnectionFailure(false)
        .followRedirects(false)
        .followSslRedirects(false)
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(25, TimeUnit.SECONDS)
        .writeTimeout(25, TimeUnit.SECONDS)
        .callTimeout(35, TimeUnit.SECONDS)
        .build()

    private suspend fun exchange(path: String, body: JSONObject? = null): Pair<Int, JSONObject> =
        withContext(Dispatchers.IO) {
            val builder = Request.Builder().url(base + path).header("Accept", "application/json")
            if (body != null) {
                val payload = body.toString().toByteArray(Charsets.UTF_8)
                builder.post(object : RequestBody() {
                    override fun contentType() = "application/json; charset=utf-8".toMediaType()
                    override fun contentLength() = payload.size.toLong()
                    override fun isOneShot() = true // Also blocks status-based follow-ups such as 503 Retry-After: 0.
                    override fun writeTo(sink: BufferedSink) { sink.write(payload) }
                })
            }
            client.newCall(builder.build()).execute().use { response ->
                val source = response.body?.source()
                val limit = 4L * 1024 * 1024
                if (source?.request(limit + 1) == true) {
                    throw ApiFailure(0, "Respuesta demasiado grande. Conservamos el intento para revisarlo.")
                }
                val raw = source?.readUtf8().orEmpty()
                val json = if (raw.isBlank()) JSONObject() else runCatching { JSONObject(raw) }
                    .getOrElse { JSONObject().put("detail", raw.take(300)) }
                response.code to json
            }
        }

    private fun failure(code: Int, json: JSONObject): ApiFailure {
        val detail = json.opt("detail")
        return ApiFailure(code, if (detail is String && detail.isNotBlank()) detail
        else "El servidor respondió $code. Revisa los datos y la conexión.")
    }

    private suspend fun request(path: String, body: JSONObject? = null): JSONObject {
        val (code, json) = exchange(path, body)
        if (code !in 200..299) throw failure(code, json)
        return json
    }

    override suspend fun bootstrap() = readBootstrap(request("/api/bootstrap"))

    override suspend fun report() = readReport(request("/api/reports/today"))

    override suspend fun parse(text: String): ParseResult =
        readParse(request("/api/cart/parse", JSONObject().put("text", text)))

    override suspend fun lookup(code: String): Product =
        readProduct(request("/api/barcode/lookup", JSONObject().put("code", code)))

    override suspend fun link(code: String, productId: Int): Product =
        readProduct(request("/api/barcode/link", JSONObject().put("code", code).put("productId", productId)))

    override suspend fun create(
        employeeId: Int,
        cart: List<CartLine>,
        paymentMethod: String,
        cashReceivedCents: Long?,
        customerId: Int?,
    ): Sale {
        val body = saleRequest(employeeId, cart, paymentMethod, cashReceivedCents, customerId)
        val (code, json) = exchange("/api/sales", body)
        // 202 (por conciliar) and 502 (PEY rejected) still carry a saleId: keep the reference.
        val reference = json.optString("saleId").ifBlank { json.optString("id") }
        if (code in setOf(200, 201, 202)) {
            if (reference.isBlank()) throw failure(code, json)
            return readSale(json)
        }
        if (code == 502 && reference.isNotBlank()) return readSale(json)
        throw failure(code, json)
    }

    override suspend fun status(saleId: String): Sale = readSale(request("/api/sales/" + saleId))

    override suspend fun adjust(employeeId: Int, productId: Int, deltaMilli: Int, reason: String): Product =
        readProduct(request("/api/inventory/adjust", JSONObject()
            .put("employeeId", employeeId)
            .put("productId", productId)
            .put("deltaMilli", deltaMilli)
            .put("reason", reason)))

    override suspend fun customers(): List<Customer> =
        request("/api/fiado/customers").optJSONArray("customers")?.objects()?.map(::readCustomer).orEmpty()

    override suspend fun addCustomer(name: String, phone: String?): Customer {
        val body = JSONObject().put("name", name)
        if (!phone.isNullOrBlank()) body.put("phone", phone)
        return readCustomer(request("/api/fiado/customers", body))
    }

    override suspend fun customer(id: Int): CustomerDetail =
        readCustomerDetail(request("/api/fiado/customers/$id"))

    override suspend fun abono(customerId: Int, amountCents: Long, employeeId: Int, note: String?): Long {
        val body = JSONObject()
            .put("amountCents", amountCents)
            .put("employeeId", employeeId)
        if (!note.isNullOrBlank()) body.put("note", note)
        val json = request("/api/fiado/customers/$customerId/abono", body)
        return json.optLong("balanceCents")
    }
}

// ---------------------------------------------------------------------------
// Offline demo repository: same shapes, no network, no real QR
// ---------------------------------------------------------------------------

class DemoRepository : ShopRepository {
    private val store = Store("tiendita-esquina", "Tiendita de la Esquina")
    private val employees = listOf(
        Employee(1, "Doña Rosa", "owner"),
        Employee(2, "Lupita", "employee"),
        Employee(3, "Toño", "employee"),
    )
    private var products = demoSeed()
    private val barcodes = mutableMapOf(
        "7500000000001" to 1, "7500000000002" to 2, "7500000000003" to 3,
        "7500000000004" to 4, "7500000000005" to 5,
    ).apply { (1..12).forEach { put("DEMO-$it", it) } }
    private val sales = mutableMapOf<String, Sale>()
    private val saleLines = mutableMapOf<String, List<CartLine>>()
    private val saleEmployees = mutableMapOf<String, Int>()
    private var customers = listOf(
        Customer(1, "Doña Mari (ejemplo)", "555-000-0001", 3500),
        Customer(2, "Cliente de la esquina", null, 0),
    )
    private val entries = mutableMapOf<Int, MutableList<FiadoEntry>>(
        1 to mutableListOf(FiadoEntry(1, "charge", 3500, "Fiado anterior (ejemplo)", System.currentTimeMillis() / 1000.0)),
    )
    private var nextEntry = 2

    override suspend fun bootstrap() = Bootstrap(store, products.toList(), employees, true, "demo")

    override suspend fun report(): Report {
        val settled = sales.values.filter { it.settled }
        val cashSales = settled.filter { it.paymentMethod == PAYMENT_CASH }
        val peySales = settled.filter { it.paymentMethod == PAYMENT_PEY }
        val fiadoSales = settled.filter { it.paymentMethod == PAYMENT_FIADO }
        val top = saleLines.filterKeys { id -> sales[id]?.settled == true }
            .values.flatten().groupBy { it.productId }.map { (id, lines) ->
                val product = products.firstOrNull { it.id == id }
                TopProduct(product?.name ?: "#$id", lines.sumOf { it.qtyMilli }, product?.unit ?: "pieza", id)
            }.sortedByDescending { it.qtyMilli }
        val byEmployee = settled.groupBy { saleEmployees[it.id] ?: 0 }.map { (id, list) ->
            EmployeeTotal(employees.firstOrNull { it.id == id }?.name ?: "Sin asignar", list.sumOf { it.totalCents }, list.size)
        }
        return Report(
            totalCents = settled.sumOf { it.totalCents },
            collectedCents = (cashSales + peySales).sumOf { it.totalCents },
            cashCents = cashSales.sumOf { it.totalCents },
            peyCents = peySales.sumOf { it.totalCents },
            fiadoCents = fiadoSales.sumOf { it.totalCents },
            salesCount = settled.size,
            byEmployee = byEmployee,
            topProducts = top,
            lowStock = products.filter { it.stockMilli <= it.lowStockMilli }
                .map { StockItem(it.name, it.stockMilli, it.unit) },
            pending = sales.values.count { it.paymentMethod == PAYMENT_PEY && it.status == "pending" },
            fiadoOutstandingCents = customers.sumOf { it.balanceCents },
            demoMode = true,
        )
    }

    override suspend fun parse(text: String) = demoParse(text, products)

    override suspend fun lookup(code: String): Product {
        val id = barcodes[code] ?: throw ApiFailure(404, "Código sin enlazar. Elige el producto para guardarlo.")
        return products.firstOrNull { it.id == id } ?: throw ApiFailure(404, "Producto desconocido.")
    }

    override suspend fun link(code: String, productId: Int): Product {
        val product = products.firstOrNull { it.id == productId } ?: throw ApiFailure(404, "Producto desconocido.")
        barcodes[code] = productId
        return product
    }

    override suspend fun create(
        employeeId: Int,
        cart: List<CartLine>,
        paymentMethod: String,
        cashReceivedCents: Long?,
        customerId: Int?,
    ): Sale {
        require(cart.isNotEmpty()) { "El carrito está vacío" }
        val byId = products.associateBy { it.id }
        val total = cart.sumOf { line ->
            lineTotalCents(byId[line.productId]?.priceCents ?: error("Actualiza el catálogo"), line.qtyMilli)
        }
        val id = "SIMULADO-" + UUID.randomUUID()
        val now = System.currentTimeMillis() / 1000.0
        val sale = when (paymentMethod) {
            PAYMENT_CASH -> {
                val received = cashReceivedCents ?: error("Falta el efectivo recibido")
                require(received >= total) { "El efectivo recibido no alcanza para el total" }
                Sale(id, total, total, "paid_cash", PAYMENT_CASH, received, received - total, createdAt = now)
            }
            PAYMENT_FIADO -> {
                val customer = customers.firstOrNull { it.id == customerId } ?: error("Elige un cliente para el fiado")
                Sale(id, total, total, "credit", PAYMENT_FIADO, customerId = customer.id,
                    customerName = customer.name, customerBalanceCents = customer.balanceCents + total, createdAt = now)
            }
            else -> Sale(id, total, 1, "pending", PAYMENT_PEY, qrId = "DEMO-QR-" + UUID.randomUUID(),
                expiresAt = now + 600, note = "SIMULADO · sin QR real", createdAt = now)
        }
        sales[id] = sale
        saleLines[id] = cart.toList()
        saleEmployees[id] = employeeId
        products = products.map { product ->
            cart.find { it.productId == product.id }?.let { product.copy(stockMilli = product.stockMilli - it.qtyMilli) } ?: product
        }
        if (paymentMethod == PAYMENT_FIADO && customerId != null) {
            customers = customers.map {
                if (it.id == customerId) it.copy(balanceCents = it.balanceCents + total) else it
            }
            entries.getOrPut(customerId) { mutableListOf() }.add(
                FiadoEntry(nextEntry++, "charge", total, "Venta simulada", now, id)
            )
        }
        return sale
    }

    override suspend fun status(saleId: String): Sale = sales[saleId] ?: error("Venta desconocida")

    override suspend fun adjust(employeeId: Int, productId: Int, deltaMilli: Int, reason: String): Product {
        val current = products.firstOrNull { it.id == productId } ?: throw ApiFailure(404, "Producto desconocido")
        val updated = current.copy(stockMilli = current.stockMilli + deltaMilli)
        products = products.map { if (it.id == productId) updated else it }
        return updated
    }

    override suspend fun customers(): List<Customer> = customers.toList()

    override suspend fun addCustomer(name: String, phone: String?): Customer {
        val customer = Customer((customers.maxOfOrNull { it.id } ?: 0) + 1, name, phone, 0)
        customers = customers + customer
        return customer
    }

    override suspend fun customer(id: Int): CustomerDetail {
        val customer = customers.firstOrNull { it.id == id } ?: throw ApiFailure(404, "Cliente desconocido")
        return CustomerDetail(customer, entries[id].orEmpty().toList())
    }

    override suspend fun abono(customerId: Int, amountCents: Long, employeeId: Int, note: String?): Long {
        require(amountCents > 0) { "El abono debe ser mayor a cero" }
        val updated = customers.map {
            if (it.id == customerId) it.copy(balanceCents = it.balanceCents - amountCents) else it
        }
        customers = updated
        entries.getOrPut(customerId) { mutableListOf() }.add(
            FiadoEntry(nextEntry++, "payment", amountCents, note, System.currentTimeMillis() / 1000.0)
        )
        return customers.first { it.id == customerId }.balanceCents
    }

    /** SIMULATED confirmation. Never produces a scannable QR or touches PEY. */
    fun simulatePaid(sale: Sale) {
        val current = sales[sale.id] ?: return
        if (current.paymentMethod != PAYMENT_PEY || current.settled) return
        sales[sale.id] = current.copy(status = "paid_pey", txId = "SIMULADO-SIN-DINERO")
    }
}

private fun demoSeed() = listOf(
    Product(1, "Coca-Cola 600 ml", "pieza", 1800, 24000, 5000, true),
    Product(2, "Sabritas sal 45 g", "pieza", 2200, 18000, 5000, true),
    Product(3, "Pan Bimbo grande", "pieza", 4800, 6000, 5000, true),
    Product(4, "Huevo (kg)", "kg", 4500, 10000, 5000, true),
    Product(5, "Leche Lala 1 L", "pieza", 3100, 12000, 5000, true),
    Product(6, "Agua Bonafont 1 L", "pieza", 1500, 20000, 5000, true),
    Product(7, "Maruchan camarón", "pieza", 1600, 30000, 5000, true),
    Product(8, "Gansito", "pieza", 1700, 15000, 5000, true),
    Product(9, "Tortillas (kg)", "kg", 2600, 8000, 5000, false),
    Product(10, "Jabón Zote", "pieza", 2300, 9000, 5000, false),
    Product(11, "Galletas Marías", "pieza", 1900, 14000, 5000, false),
    Product(12, "Fanta 600 ml", "pieza", 1700, 12000, 5000, false),
)

internal fun recoverJournal(raw: String?, creating: Boolean): Pair<Sale?, Boolean> {
    if (raw == null) return null to creating
    val sale = runCatching { readSale(JSONObject(raw)) }.getOrNull()
    return sale to (creating || sale == null)
}
