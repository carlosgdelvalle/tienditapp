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
import java.net.URLEncoder
import java.util.UUID
import java.util.concurrent.TimeUnit

class ApiFailure(val code: Int, message: String) : Exception(message)

interface ShopRepository {
    /**
     * Identidad simulada: el servidor valida X-Employee-Id y aplica rol/permisos.
     * Null conserva el comportamiento abierto v1 (antes de elegir perfil).
     */
    fun actAs(employeeId: Int?)
    suspend fun bootstrap(): Bootstrap
    suspend fun report(): Report
    /** Crea (o recupera) el ticket de soporte de un cobro que quedó sin confirmar. */
    suspend fun reportTicket(saleId: String?, note: String?): SupportTicket
    suspend fun profile(): StoreProfile
    suspend fun updateProfile(name: String? = null, businessType: String? = null, ownerName: String? = null): StoreProfile
    suspend fun uploadPhoto(dataUrl: String)
    suspend fun employees(): List<Employee>
    suspend fun patchEmployee(
        id: Int,
        name: String? = null,
        nickname: String? = null,
        active: Boolean? = null,
        canSell: Boolean? = null,
        canFiado: Boolean? = null,
        canInventory: Boolean? = null,
    ): Employee
    suspend fun createInvite(name: String, canSell: Boolean, canFiado: Boolean, canInventory: Boolean): Invite
    suspend fun inviteInfo(token: String): InviteInfo
    suspend fun acceptInvite(token: String, nickname: String): Employee
    suspend fun inventory(): InventorySnapshot
    suspend fun inventorySet(productId: Int, qtyMilli: Int, note: String? = null): Product
    suspend fun inventoryVoice(text: String): VoiceResult
    // Contrato v3 · catálogo generalizado, plantillas, tareas del día y gastos.
    suspend fun catalog(query: String? = null, category: String? = null, kind: String? = null, limit: Int = 500, offset: Int = 0): CatalogPage
    suspend fun createCatalogItem(draft: CatalogDraft): Product
    suspend fun updateCatalogItem(id: Int, draft: CatalogDraft): Product
    suspend fun deleteCatalogItem(id: Int)
    /** SOLO aplica si la tienda aún no tiene catálogo; el servidor responde 409 si ya hay. */
    suspend fun applyTemplate(businessType: String)
    suspend fun tasks(): List<DayTask>
    suspend fun patchTask(
        id: Int,
        assignedEmployeeId: Int? = null,
        clearAssignee: Boolean = false,
        active: Boolean? = null,
        title: String? = null,
    ): DayTask
    suspend fun expenses(limit: Int = 50): List<Expense>
    suspend fun addExpense(amountCents: Long, note: String? = null): Expense
    suspend fun expenseVoice(text: String): ExpenseDraft
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
    suspend fun cancel(saleId: String): Sale
    suspend fun adjust(employeeId: Int, productId: Int, deltaMilli: Int, reason: String): Product
    suspend fun customers(): List<Customer>
    suspend fun addCustomer(name: String, phone: String?): Customer
    suspend fun customer(id: Int): CustomerDetail
    /** Contrato v3.2 · historial de cargos y abonos, más reciente primero. */
    suspend fun fiadoEntries(customerId: Int): List<FiadoEntry>
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
/** Contrato v3.1 · imagen opcional; tolera null, vacío y el alias snake_case. */
internal fun JSONObject.optionalImageUrl(): String? =
    (nullableString("imageUrl") ?: nullableString("image_url"))?.trim()?.takeIf { it.isNotEmpty() }

internal fun readProduct(j: JSONObject) = Product(
    id = j.optInt("id"),
    name = j.optString("name"),
    unit = j.optString("unit", "pieza").ifBlank { "pieza" },
    priceCents = j.optLong("priceCents"),
    stockMilli = j.optInt("stockMilli"),
    lowStockMilli = j.optInt("lowStockMilli", 5000),
    quick = j.optBoolean("quick"),
    unlimitedStock = j.optBoolean("unlimitedStock", false),
    kind = j.optString("kind", KIND_PRODUCTO).ifBlank { KIND_PRODUCTO },
    category = j.nullableString("category"),
    durationMinutes = j.nullableInt("durationMinutes"),
    aliases = j.optJSONArray("aliases")?.strings().orEmpty(),
    imageUrl = j.optionalImageUrl(),
)

/** Lee la página del catálogo v3; acepta {items,total} o una lista suelta ya envuelta. */
internal fun readCatalog(j: JSONObject) = CatalogPage(
    items = j.optJSONArray("items")?.objects()?.map(::readProduct).orEmpty(),
    total = if (j.has("total")) j.optInt("total") else j.optJSONArray("items")?.length() ?: 0,
)

internal fun readTask(j: JSONObject) = DayTask(
    id = j.optInt("id"),
    key = j.optString("key"),
    title = j.optString("title").ifBlank { j.optString("name") },
    assignedEmployeeId = j.nullableInt("assignedEmployeeId") ?: j.nullableInt("assigned_employee_id"),
    active = j.optBoolean("active", true),
)

internal fun readExpense(j: JSONObject) = Expense(
    id = j.optInt("id"),
    amountCents = j.optLong("amountCents"),
    note = j.nullableString("note"),
    createdAt = j.optDouble("createdAt", 0.0),
    employeeId = j.nullableInt("employeeId"),
    employeeName = j.nullableString("employeeName") ?: j.nullableString("reportedByName"),
)

internal fun readExpenseVoice(j: JSONObject) = ExpenseDraft(
    amountCents = if (j.has("amountCents") && !j.isNull("amountCents")) j.optLong("amountCents") else 0L,
    note = j.nullableString("note"),
)

/** Cuerpo de alta/edición tal como lo pide el contrato v3 (nombre, precio, unidad, kind…). */
internal fun catalogBody(draft: CatalogDraft, includeNulls: Boolean = true) = JSONObject()
    .put("name", draft.name.trim())
    .put("unit", draft.unit)
    .put("priceCents", draft.priceCents)
    .put("aliases", JSONArray(draft.aliases))
    .put("stockMilli", draft.stockMilli ?: 0)
    .put("unlimitedStock", draft.unlimitedStock || !kindTracksStock(draft.kind))
    .put("kind", draft.kind)
    .apply {
        if (includeNulls) {
            put("category", draft.category ?: JSONObject.NULL)
            put("durationMinutes", draft.durationMinutes ?: JSONObject.NULL)
            // v3.1: null explícito borra la imagen al editar; el servidor la acepta opcional.
            put("imageUrl", normalizedImageUrl(draft.imageUrl) ?: JSONObject.NULL)
        } else {
            draft.category?.let { put("category", it) }
            draft.durationMinutes?.let { put("durationMinutes", it) }
            normalizedImageUrl(draft.imageUrl)?.let { put("imageUrl", it) }
        }
    }
    .put("quick", draft.quick)


internal fun readEmployee(j: JSONObject) = Employee(
    id = j.optInt("id"),
    name = j.optString("name"),
    role = j.optString("role", "employee").ifBlank { "employee" },
    nickname = j.nullableString("nickname"),
    active = j.optBoolean("active", true),
    canSell = j.optBoolean("canSell", true),
    canFiado = j.optBoolean("canFiado", true),
    canInventory = j.optBoolean("canInventory", false),
)

internal fun readStoreProfile(j: JSONObject) = StoreProfile(
    storeId = j.optString("storeId").ifBlank { j.optString("id") },
    name = j.optString("name"),
    businessType = j.optString("businessType"),
    ownerName = j.optString("ownerName"),
)

internal fun readInvite(j: JSONObject) = Invite(
    token = j.optString("token"),
    employeeId = j.optInt("employeeId"),
    url = j.optString("url"),
)

internal fun readInviteInfo(j: JSONObject): InviteInfo {
    val permissions = j.optJSONObject("permissions")
    fun flag(key: String, fallback: Boolean) = when {
        j.has(key) -> j.optBoolean(key)
        permissions?.has(key) == true -> permissions.optBoolean(key)
        else -> fallback
    }
    return InviteInfo(
        token = j.optString("token"),
        employeeId = j.optInt("employeeId"),
        name = j.optString("name"),
        storeName = j.optString("storeName"),
        businessType = j.optString("businessType"),
        canSell = flag("canSell", true),
        canFiado = flag("canFiado", true),
        canInventory = flag("canInventory", false),
    )
}

internal fun readVoiceLine(j: JSONObject) = VoiceLine(
    productId = j.optInt("productId"),
    name = j.optString("name"),
    qtyMilli = if (j.has("qtyMilli") && !j.isNull("qtyMilli")) j.optInt("qtyMilli") else null,
    unit = j.optString("unit", "pieza").ifBlank { "pieza" },
)

internal fun readVoice(j: JSONObject) = VoiceResult(
    items = j.optJSONArray("items")?.objects()?.map(::readVoiceLine).orEmpty(),
    note = j.nullableString("note"),
)

internal fun readInventoryItem(j: JSONObject) = InventoryItem(
    productId = j.optInt("productId"),
    name = j.optString("name"),
    unit = j.optString("unit", "pieza").ifBlank { "pieza" },
    stockMilli = j.optInt("stockMilli"),
    unlimitedStock = j.optBoolean("unlimitedStock", false),
    lastUpdatedAt = if (j.has("lastUpdatedAt") && !j.isNull("lastUpdatedAt")) j.optDouble("lastUpdatedAt") else null,
    lastUpdatedByName = j.nullableString("lastUpdatedByName"),
    lastUpdatedByNickname = j.nullableString("lastUpdatedByNickname"),
    imageUrl = j.optionalImageUrl(),
)

internal fun readInventory(j: JSONObject) = InventorySnapshot(
    items = j.optJSONArray("items")?.objects()?.map(::readInventoryItem).orEmpty(),
    totalValueCents = j.optLong("totalValueCents"),
)

internal fun readBootstrap(j: JSONObject): Bootstrap {
    val storeJson = j.optJSONObject("store")
    val store = Store(
        id = storeJson?.optString("id").orEmpty(),
        name = storeJson?.optString("name")?.takeIf { it.isNotBlank() } ?: j.optString("store"),
        businessType = storeJson?.optString("businessType").orEmpty(),
        ownerName = storeJson?.optString("ownerName").orEmpty(),
    )
    return Bootstrap(
        store = store,
        products = j.optJSONArray("products")?.objects()?.map(::readProduct).orEmpty(),
        employees = j.optJSONArray("employees")?.objects()?.map(::readEmployee).orEmpty(),
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
    totalExpensesCents = j.optLong("totalExpensesCents"),
)

/** Parsea el ticket de soporte con campos opcionales: ningún dato faltante rompe el teléfono. */
internal fun readSupportTicket(j: JSONObject) = SupportTicket(
    id = j.optString("id").ifBlank { j.optString("ticketId") }.trim(),
    saleId = j.nullableString("saleId"),
    saleStatus = j.nullableString("saleStatus"),
    saleTotalCents = j.optLong("saleTotalCents"),
    chargedCents = j.optLong("chargedCents"),
    peyTxId = j.nullableString("peyTxId"),
    note = j.nullableString("note"),
    status = j.optString("status", "open").ifBlank { "open" },
    createdAt = j.optDouble("createdAt", 0.0),
    reportedByName = j.nullableString("reportedByName"),
    alreadyOpen = j.optBoolean("alreadyOpen", false),
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

/** Contrato v3.2: cargo o abono, con el nombre de quien lo registró. */
internal fun readFiadoEntry(j: JSONObject) = FiadoEntry(
    id = j.optInt("id"),
    kind = j.optString("kind", "charge"),
    amountCents = j.optLong("amountCents"),
    note = j.nullableString("note"),
    createdAt = j.optDouble("createdAt", 0.0),
    saleId = j.nullableString("saleId"),
    employeeName = j.nullableString("employeeName"),
)

internal fun readCustomerDetail(j: JSONObject): CustomerDetail {
    val customerJson = j.optJSONObject("customer") ?: j
    val entries = j.optJSONArray("entries")?.objects()?.map(::readFiadoEntry).orEmpty()
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

    private var acting: Int? = null

    override fun actAs(employeeId: Int?) { acting = employeeId }

    private suspend fun exchange(path: String, body: JSONObject? = null, method: String? = null): Pair<Int, JSONObject> =
        withContext(Dispatchers.IO) {
            val builder = Request.Builder().url(base + path).header("Accept", "application/json")
            // Identidad simulada: después de elegir perfil el servidor valida rol y permisos.
            acting?.let { builder.header("X-Employee-Id", it.toString()) }
            if (body != null) {
                val payload = body.toString().toByteArray(Charsets.UTF_8)
                builder.method(method ?: "POST", object : RequestBody() {
                    override fun contentType() = "application/json; charset=utf-8".toMediaType()
                    override fun contentLength() = payload.size.toLong()
                    override fun isOneShot() = true // Also blocks status-based follow-ups such as 503 Retry-After: 0.
                    override fun writeTo(sink: BufferedSink) { sink.write(payload) }
                })
            } else if (method != null) {
                builder.method(method, null)
            }
            client.newCall(builder.build()).execute().use { response ->
                val source = response.body?.source()
                val limit = 4L * 1024 * 1024
                if (source?.request(limit + 1) == true) {
                    throw ApiFailure(0, "Respuesta demasiado grande. Conservamos el intento para revisarlo.")
                }
                val raw = source?.readUtf8().orEmpty()
                val json = if (raw.isBlank()) JSONObject() else runCatching { JSONObject(raw) }
                    .getOrElse {
                        // Algunos endpoints v3 (tareas, gastos) pueden responder una lista
                        // suelta; la app la envuelve como {items:[...]} sin tronar.
                        runCatching { JSONObject().put("items", JSONArray(raw)) }
                            .getOrElse { JSONObject().put("detail", raw.take(300)) }
                    }
                response.code to json
            }
        }

    private fun failure(code: Int, json: JSONObject): ApiFailure {
        val detail = json.opt("detail")
        return ApiFailure(code, if (detail is String && detail.isNotBlank()) detail
        else "El servidor respondió $code. Revisa los datos y la conexión.")
    }

    private suspend fun request(path: String, body: JSONObject? = null, method: String? = null): JSONObject {
        val (code, json) = exchange(path, body, method)
        if (code !in 200..299) throw failure(code, json)
        return json
    }

    override suspend fun bootstrap() = readBootstrap(request("/api/bootstrap"))

    override suspend fun report() = readReport(request("/api/reports/today"))

    override suspend fun reportTicket(saleId: String?, note: String?): SupportTicket {
        val body = JSONObject()
        if (!saleId.isNullOrBlank()) body.put("saleId", saleId)
        if (!note.isNullOrBlank()) body.put("note", note)
        return readSupportTicket(request("/api/support/tickets", body))
    }

    override suspend fun profile() = readStoreProfile(request("/api/store/profile"))

    override suspend fun updateProfile(name: String?, businessType: String?, ownerName: String?): StoreProfile {
        val body = JSONObject()
        if (name != null) body.put("name", name)
        if (businessType != null) body.put("businessType", businessType)
        if (ownerName != null) body.put("ownerName", ownerName)
        return readStoreProfile(request("/api/store/profile", body, "PUT"))
    }

    override suspend fun uploadPhoto(dataUrl: String) {
        request("/api/store/photo", JSONObject().put("dataUrl", dataUrl))
    }

    override suspend fun employees(): List<Employee> =
        request("/api/employees").optJSONArray("items")?.objects()?.map(::readEmployee).orEmpty()

    override suspend fun patchEmployee(
        id: Int,
        name: String?,
        nickname: String?,
        active: Boolean?,
        canSell: Boolean?,
        canFiado: Boolean?,
        canInventory: Boolean?,
    ): Employee {
        val body = JSONObject()
        if (name != null) body.put("name", name)
        if (nickname != null) body.put("nickname", nickname)
        if (active != null) body.put("active", active)
        if (canSell != null) body.put("canSell", canSell)
        if (canFiado != null) body.put("canFiado", canFiado)
        if (canInventory != null) body.put("canInventory", canInventory)
        return readEmployee(request("/api/employees/$id", body, "PATCH"))
    }

    override suspend fun createInvite(name: String, canSell: Boolean, canFiado: Boolean, canInventory: Boolean): Invite =
        readInvite(request("/api/employees/invites", JSONObject()
            .put("name", name)
            .put("canSell", canSell)
            .put("canFiado", canFiado)
            .put("canInventory", canInventory)))

    override suspend fun inviteInfo(token: String) =
        readInviteInfo(request("/api/employees/invites/" + token))

    override suspend fun acceptInvite(token: String, nickname: String): Employee =
        readEmployee(request("/api/employees/invites/$token/accept", JSONObject().put("nickname", nickname)))

    override suspend fun inventory() = readInventory(request("/api/inventory"))

    override suspend fun inventorySet(productId: Int, qtyMilli: Int, note: String?): Product {
        val body = JSONObject().put("productId", productId).put("qtyMilli", qtyMilli)
        if (!note.isNullOrBlank()) body.put("note", note)
        return readProduct(request("/api/inventory/set", body))
    }

    override suspend fun inventoryVoice(text: String): VoiceResult =
        readVoice(request("/api/inventory/voice", JSONObject().put("text", text)))

    // --- Contrato v3 · catálogo, plantillas, tareas y gastos -----------------

    override suspend fun catalog(
        query: String?,
        category: String?,
        kind: String?,
        limit: Int,
        offset: Int,
    ): CatalogPage {
        val params = mutableListOf<Pair<String, String>>()
        query?.trim()?.takeIf { it.isNotBlank() }?.let { params += "q" to it }
        category?.takeIf { it.isNotBlank() }?.let { params += "category" to it }
        kind?.takeIf { it.isNotBlank() }?.let { params += "kind" to it }
        params += "limit" to limit.coerceIn(1, 500).toString()
        params += "offset" to offset.coerceAtLeast(0).toString()
        val qs = params.joinToString("&") { (key, value) ->
            key + "=" + URLEncoder.encode(value, "UTF-8")
        }
        return readCatalog(request("/api/catalog?" + qs))
    }

    override suspend fun createCatalogItem(draft: CatalogDraft): Product =
        readProduct(request("/api/catalog", catalogBody(draft)))

    override suspend fun updateCatalogItem(id: Int, draft: CatalogDraft): Product =
        readProduct(request("/api/catalog/" + id, catalogBody(draft), "PATCH"))

    override suspend fun deleteCatalogItem(id: Int) {
        request("/api/catalog/" + id, null, "DELETE")
    }

    override suspend fun applyTemplate(businessType: String) {
        request("/api/catalog/templates/apply", JSONObject().put("businessType", businessType))
    }

    override suspend fun tasks(): List<DayTask> =
        request("/api/tasks").optJSONArray("items")?.objects()?.map(::readTask).orEmpty()

    override suspend fun patchTask(
        id: Int,
        assignedEmployeeId: Int?,
        clearAssignee: Boolean,
        active: Boolean?,
        title: String?,
    ): DayTask {
        val body = JSONObject()
        when {
            clearAssignee -> body.put("assignedEmployeeId", JSONObject.NULL)
            assignedEmployeeId != null -> body.put("assignedEmployeeId", assignedEmployeeId)
        }
        if (active != null) body.put("active", active)
        if (title != null) body.put("title", title)
        return readTask(request("/api/tasks/" + id, body, "PATCH"))
    }

    override suspend fun expenses(limit: Int): List<Expense> =
        request("/api/expenses?limit=" + limit.coerceIn(1, 500))
            .optJSONArray("items")?.objects()?.map(::readExpense).orEmpty()

    override suspend fun addExpense(amountCents: Long, note: String?): Expense {
        val body = JSONObject().put("amountCents", amountCents)
        if (!note.isNullOrBlank()) body.put("note", note)
        return readExpense(request("/api/expenses", body))
    }

    override suspend fun expenseVoice(text: String): ExpenseDraft =
        readExpenseVoice(request("/api/expenses/voice", JSONObject().put("text", text)))

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
    override suspend fun cancel(saleId: String): Sale = readSale(
        request("/api/sales/$saleId/cancel?pendingOnly=true", JSONObject()),
    )

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

    override suspend fun fiadoEntries(customerId: Int): List<FiadoEntry> =
        request("/api/fiado/customers/$customerId/entries")
            .optJSONArray("items")?.objects()?.map(::readFiadoEntry).orEmpty()

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

class DemoRepository(
    seed: List<Product> = demoSeed(),
    taskSeed: List<DayTask> = demoTaskSeed(),
) : ShopRepository {
    // Demo genérica (contrato v3): «Mi negocio», no una tienda con nombre propio.
    private var store = Store("mi-negocio", "Mi negocio", "Tiendita/Abarrotes", "Doña Rosa")
    private var profile = StoreProfile("mi-negocio", "Mi negocio", "Tiendita/Abarrotes", "Doña Rosa")
    private var acting: Int? = null
    private var photoDataUrl: String? = null

    // Personas ficticias con permisos distintos para probar el contrato v2 sin red.
    private val team = mutableListOf(
        Employee(1, "Doña Rosa", "owner", canInventory = true),
        Employee(2, "Lupita", "employee", nickname = "Lupis", canInventory = true),
        Employee(3, "Toño", "employee", canSell = false, canFiado = false, canInventory = false),
        Employee(4, "Invitada pendiente", "employee", active = false, canInventory = true),
        Employee(5, "Beto", "employee", canSell = true, canFiado = false, canInventory = false),
    )
    private val invites = mutableMapOf("INVITACION-DEMO" to 4)
    private val acceptedTokens = mutableSetOf<String>()
    private val lastUpdate = mutableMapOf<Int, Movement>()
    private var products: List<Product> = seed.toList()
    private var nextProductId = (products.maxOfOrNull { it.id } ?: 0) + 1
    // Contrato v3: tareas del día, gastos y catálogo también viven en la simulación.
    private val dayTasks = taskSeed.toMutableList()
    private var nextTaskId = (dayTasks.maxOfOrNull { it.id } ?: 0) + 1
    private val expenses = mutableListOf<Expense>()
    private var nextExpenseId = 1

    private data class Movement(val at: Double, val name: String, val nickname: String?)

    override fun actAs(employeeId: Int?) { acting = employeeId }

    private fun actor(): Employee? {
        val id = acting ?: return null
        return team.firstOrNull { it.id == id } ?: throw ApiFailure(403, "Este perfil ya no tiene acceso")
    }

    private fun ownerActor(): Employee {
        val actor = actor() ?: return team.first { it.isOwner }
        if (!actor.isOwner) throw ApiFailure(403, "Solo el dueño ve el equipo")
        return actor
    }

    private fun requireInventoryPermission() {
        val actor = actor() ?: return
        if (!actor.isOwner && !actor.canInventory) {
            throw ApiFailure(403, "Tu perfil no puede editar el inventario")
        }
    }

    /** Contrato v3.2: el servidor rechaza abonos e historial de empleados sin canFiado. */
    private fun requireFiadoPermission() {
        val actor = actor() ?: return
        if (!actor.isOwner && !actor.canFiado) {
            throw ApiFailure(403, "Tu perfil no puede registrar abonos")
        }
    }

    private fun recordMovement(productId: Int, fallbackName: String = "Doña Rosa") {
        val actor = runCatching { actor() }.getOrNull()
        lastUpdate[productId] = Movement(
            at = System.currentTimeMillis() / 1000.0,
            name = actor?.name ?: fallbackName,
            nickname = actor?.nickname,
        )
    }
    private val barcodes = mutableMapOf(
        "7500000000001" to 1, "7500000000002" to 2, "7500000000003" to 3,
        "7500000000004" to 4, "7500000000005" to 5,
    ).apply { (1..12).forEach { put("DEMO-$it", it) } }
    private val sales = mutableMapOf<String, Sale>()
    private val saleLines = mutableMapOf<String, List<CartLine>>()
    private val saleEmployees = mutableMapOf<String, Int>()
    // Tickets SIMULADOS: un solo ticket abierto por venta, como el servidor real.
    private val supportTickets = mutableMapOf<String, SupportTicket>()
    private var customers = listOf(
        Customer(1, "Doña Mari (ejemplo)", "555-000-0001", 3500),
        Customer(2, "Cliente de la esquina", null, 0),
    )
    // Contrato v3.2 · historial ficticio por cliente con cargos y abonos de ejemplo.
    private val entries = mutableMapOf<Int, MutableList<FiadoEntry>>().apply {
        val seedNow = System.currentTimeMillis() / 1000.0
        put(1, mutableListOf(
            FiadoEntry(1, "charge", 3500, "Fiado anterior (ejemplo)", seedNow - 86_400.0,
                employeeName = "Doña Rosa"),
        ))
        put(2, mutableListOf(
            FiadoEntry(2, "charge", 1200, "Venta a crédito (ejemplo)", seedNow - 172_800.0,
                employeeName = "Lupita"),
            FiadoEntry(3, "payment", 1200, "Abono (ejemplo)", seedNow - 86_400.0,
                employeeName = "Doña Rosa"),
        ))
    }
    private var nextEntry = 4

    override suspend fun bootstrap() = Bootstrap(store, products.toList(), team.filter { it.active }, true, "demo")

    override suspend fun profile(): StoreProfile = profile

    override suspend fun updateProfile(name: String?, businessType: String?, ownerName: String?): StoreProfile {
        profile = profile.copy(
            name = name?.takeIf { it.isNotBlank() } ?: profile.name,
            businessType = businessType?.takeIf { it.isNotBlank() } ?: profile.businessType,
            ownerName = ownerName?.takeIf { it.isNotBlank() } ?: profile.ownerName,
        )
        store = store.copy(
            name = profile.name,
            businessType = profile.businessType,
            ownerName = profile.ownerName,
        )
        return profile
    }

    override suspend fun uploadPhoto(dataUrl: String) {
        require(dataUrl.startsWith("data:image/jpeg;base64,") || dataUrl.startsWith("data:image/png;base64,")) {
            "La foto debe ser JPEG o PNG en data URL"
        }
        require(dataUrl.length <= 5_000_000) { "La foto supera los 5 MB" }
        photoDataUrl = dataUrl
    }

    override suspend fun employees(): List<Employee> {
        ownerActor()
        return team.toList()
    }

    override suspend fun patchEmployee(
        id: Int,
        name: String?,
        nickname: String?,
        active: Boolean?,
        canSell: Boolean?,
        canFiado: Boolean?,
        canInventory: Boolean?,
    ): Employee {
        ownerActor()
        val current = team.firstOrNull { it.id == id } ?: throw ApiFailure(404, "Empleado desconocido")
        if (current.isOwner && active == false) throw ApiFailure(400, "El dueño no puede desactivarse")
        val updated = current.copy(
            name = name?.takeIf { it.isNotBlank() } ?: current.name,
            nickname = nickname ?: current.nickname,
            active = active ?: current.active,
            canSell = canSell ?: current.canSell,
            canFiado = canFiado ?: current.canFiado,
            canInventory = canInventory ?: current.canInventory,
        )
        team[team.indexOf(current)] = updated
        return updated
    }

    override suspend fun createInvite(name: String, canSell: Boolean, canFiado: Boolean, canInventory: Boolean): Invite {
        ownerActor()
        require(name.isNotBlank()) { "Escribe el nombre de la persona" }
        val id = (team.maxOfOrNull { it.id } ?: 0) + 1
        team += Employee(id, name.trim(), "employee", active = false, canSell = canSell, canFiado = canFiado, canInventory = canInventory)
        val token = UUID.randomUUID().toString().replace("-", "")
        invites[token] = id
        return Invite(token, id, "https://abarpay-api.onrender.com/invite/$token")
    }

    override suspend fun inviteInfo(token: String): InviteInfo {
        val employeeId = invites[token] ?: throw ApiFailure(404, "La invitación no existe o venció")
        if (token in acceptedTokens) throw ApiFailure(410, "Esta invitación ya se usó")
        val employee = team.firstOrNull { it.id == employeeId } ?: throw ApiFailure(404, "La invitación no existe")
        return InviteInfo(
            token = token,
            employeeId = employee.id,
            name = employee.name,
            storeName = store.name,
            businessType = store.businessType,
            canSell = employee.canSell,
            canFiado = employee.canFiado,
            canInventory = employee.canInventory,
        )
    }

    override suspend fun acceptInvite(token: String, nickname: String): Employee {
        val employeeId = invites[token] ?: throw ApiFailure(404, "La invitación no existe o venció")
        if (token in acceptedTokens) throw ApiFailure(410, "Esta invitación ya se usó")
        require(nickname.isNotBlank()) { "Escribe tu apodo" }
        val current = team.firstOrNull { it.id == employeeId } ?: throw ApiFailure(404, "La invitación no existe")
        val updated = current.copy(nickname = nickname.trim(), active = true)
        team[team.indexOf(current)] = updated
        acceptedTokens += token
        return updated
    }

    override suspend fun inventory(): InventorySnapshot {
        val items = products.map { product ->
            val movement = lastUpdate[product.id]
            InventoryItem(
                productId = product.id,
                name = product.name,
                unit = product.unit,
                stockMilli = product.stockMilli,
                unlimitedStock = product.unlimitedStock,
                lastUpdatedAt = movement?.at,
                lastUpdatedByName = movement?.name,
                lastUpdatedByNickname = movement?.nickname,
                imageUrl = product.imageUrl,
            )
        }
        val total = products.sumOf { product ->
            if (product.unlimitedStock) 0L else Math.floorDiv(product.priceCents * product.stockMilli + 500L, 1000L)
        }
        return InventorySnapshot(items, total)
    }

    override suspend fun inventorySet(productId: Int, qtyMilli: Int, note: String?): Product {
        requireInventoryPermission()
        val current = products.firstOrNull { it.id == productId } ?: throw ApiFailure(404, "Producto desconocido")
        if (current.unlimitedStock) throw ApiFailure(400, "Este producto tiene inventario sin límite")
        val updated = current.copy(stockMilli = qtyMilli)
        products = products.map { if (it.id == productId) updated else it }
        recordMovement(productId)
        return updated
    }

    override suspend fun inventoryVoice(text: String): VoiceResult {
        val parsed = demoParse(text, products)
        val items = parsed.items.map { VoiceLine(it.productId, it.name, it.qtyMilli, it.unit) }
        return VoiceResult(
            items = items,
            note = if (parsed.unmatched.isEmpty()) null else "No encontré: " + parsed.unmatched.joinToString(", "),
        )
    }

    // --- Contrato v3 · catálogo, plantillas, tareas y gastos -----------------

    override suspend fun catalog(
        query: String?,
        category: String?,
        kind: String?,
        limit: Int,
        offset: Int,
    ): CatalogPage {
        val filtered = products.filter { catalogMatches(it, query.orEmpty(), category, kind) }
        return CatalogPage(
            items = filtered.drop(offset.coerceAtLeast(0)).take(limit.coerceIn(1, 500)),
            total = filtered.size,
        )
    }

    override suspend fun createCatalogItem(draft: CatalogDraft): Product {
        ownerActor()
        validateCatalogDraft(draft)
        val unlimited = draft.unlimitedStock || !kindTracksStock(draft.kind)
        val product = Product(
            id = nextProductId++,
            name = draft.name.trim(),
            unit = draft.unit,
            priceCents = draft.priceCents,
            stockMilli = if (unlimited) 0 else (draft.stockMilli ?: 0),
            quick = draft.quick,
            unlimitedStock = unlimited,
            kind = draft.kind,
            category = draft.category?.trim()?.takeIf { it.isNotBlank() },
            durationMinutes = draft.durationMinutes,
            aliases = draft.aliases,
            imageUrl = normalizedImageUrl(draft.imageUrl),
        )
        products += product
        return product
    }

    override suspend fun updateCatalogItem(id: Int, draft: CatalogDraft): Product {
        ownerActor()
        validateCatalogDraft(draft)
        val current = products.firstOrNull { it.id == id }
            ?: throw ApiFailure(404, "Ese artículo ya no está en el catálogo")
        val unlimited = draft.unlimitedStock || !kindTracksStock(draft.kind)
        val updated = current.copy(
            name = draft.name.trim(),
            unit = draft.unit,
            priceCents = draft.priceCents,
            stockMilli = if (unlimited) 0 else (draft.stockMilli ?: current.stockMilli),
            quick = draft.quick,
            unlimitedStock = unlimited,
            kind = draft.kind,
            category = draft.category?.trim()?.takeIf { it.isNotBlank() },
            durationMinutes = draft.durationMinutes,
            aliases = draft.aliases,
            imageUrl = normalizedImageUrl(draft.imageUrl),
        )
        products = products.map { if (it.id == id) updated else it }
        return updated
    }

    override suspend fun deleteCatalogItem(id: Int) {
        ownerActor()
        products.firstOrNull { it.id == id } ?: throw ApiFailure(404, "Ese artículo ya no está en el catálogo")
        // Igual que el servidor: 409 si el artículo ya tiene ventas o movimientos.
        val hasSales = saleLines.values.any { lines -> lines.any { it.productId == id } }
        val hasMovements = lastUpdate.containsKey(id)
        if (hasSales || hasMovements) {
            throw ApiFailure(409, "No se puede borrar: tiene ventas o movimientos")
        }
        products = products.filterNot { it.id == id }
    }

    /**
     * El demo SIMULA un negocio nuevo: reproduce el catálogo y las tareas fijas
     * del tipo elegido, sin red. En API el servidor responde 409 si ya había
     * catálogo y la app lo ignora.
     */
    override suspend fun applyTemplate(businessType: String) {
        ownerActor()
        val key = templateBusinessType(businessType)
        val items = demoTemplateItems(key)
        if (items.isEmpty()) throw ApiFailure(400, "No hay plantilla para ese tipo de negocio")
        products = items.toMutableList()
        nextProductId = (products.maxOfOrNull { it.id } ?: 0) + 1
        dayTasks.clear()
        demoTemplateTasks(key).forEachIndexed { index, task ->
            dayTasks += DayTask(index + 1, task.key, task.title, assignedEmployeeId = null, active = true)
        }
        nextTaskId = dayTasks.size + 1
    }

    override suspend fun tasks(): List<DayTask> {
        val actor = actor()
        return if (actor != null && !actor.isOwner) {
            dayTasks.filter { it.active && it.assignedEmployeeId == actor.id }
        } else {
            dayTasks.toList()
        }
    }

    override suspend fun patchTask(
        id: Int,
        assignedEmployeeId: Int?,
        clearAssignee: Boolean,
        active: Boolean?,
        title: String?,
    ): DayTask {
        ownerActor()
        val current = dayTasks.firstOrNull { it.id == id } ?: throw ApiFailure(404, "Tarea desconocida")
        val updated = current.copy(
            title = title?.takeIf { it.isNotBlank() } ?: current.title,
            assignedEmployeeId = when {
                clearAssignee -> null
                assignedEmployeeId != null -> assignedEmployeeId
                else -> current.assignedEmployeeId
            },
            active = active ?: current.active,
        )
        dayTasks[dayTasks.indexOf(current)] = updated
        return updated
    }

    override suspend fun expenses(limit: Int): List<Expense> {
        ownerActor()
        return expenses.sortedByDescending { it.createdAt }.take(limit.coerceIn(1, 500))
    }

    override suspend fun addExpense(amountCents: Long, note: String?): Expense {
        require(amountCents > 0) { "Escribe un monto mayor a cero" }
        val actor = actor()
        val expense = Expense(
            id = nextExpenseId++,
            amountCents = amountCents,
            note = note?.trim()?.takeIf { it.isNotBlank() },
            createdAt = System.currentTimeMillis() / 1000.0,
            employeeId = actor?.id,
            employeeName = actor?.displayName ?: store.ownerName,
        )
        expenses += expense
        return expense
    }

    override suspend fun expenseVoice(text: String): ExpenseDraft =
        parseExpenseVoice(text) ?: ExpenseDraft(0, "No entendí el monto")

    override suspend fun report(): Report {
        val actor = actor()
        if (actor != null && !actor.isOwner) throw ApiFailure(403, "Solo el dueño ve reportes")
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
            EmployeeTotal(team.firstOrNull { it.id == id }?.displayName ?: "Sin asignar", list.sumOf { it.totalCents }, list.size)
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
            lowStock = products.filter { it.isLowStock }
                .map { StockItem(it.name, it.stockMilli, it.unit) },
            pending = sales.values.count { it.paymentMethod == PAYMENT_PEY && it.status == "pending" },
            fiadoOutstandingCents = customers.sumOf { it.balanceCents },
            demoMode = true,
            totalExpensesCents = expenses.filter { isTodaySeconds(it.createdAt) }.sumOf { it.amountCents },
        )
    }

    override suspend fun reportTicket(saleId: String?, note: String?): SupportTicket {
        val cleanSale = saleId?.trim()?.takeIf { it.isNotBlank() }
        val cleanNote = note?.trim()?.takeIf { it.isNotBlank() }
        if (cleanSale == null && cleanNote == null) throw ApiFailure(400, "Escribe una nota para el ticket")
        val sale = cleanSale?.let { id -> sales[id] ?: throw ApiFailure(404, "Venta desconocida") }
        // Igual que el servidor: si ya hay un ticket abierto para la venta, se devuelve ese.
        if (cleanSale != null) {
            supportTickets.values.firstOrNull { it.saleId == cleanSale && it.status == "open" }?.let {
                return it.copy(alreadyOpen = true)
            }
        }
        val actor = runCatching { actor() }.getOrNull()
        val ticket = SupportTicket(
            id = "tkt_" + UUID.randomUUID().toString().replace("-", "").take(12),
            saleId = cleanSale,
            saleStatus = sale?.status,
            saleTotalCents = sale?.totalCents ?: 0,
            chargedCents = sale?.chargedCents ?: 0,
            peyTxId = sale?.txId,
            note = cleanNote,
            status = "open",
            createdAt = System.currentTimeMillis() / 1000.0,
            // Igual que el servidor: el nombre propio de quien reporta (sin apodo).
            reportedByName = actor?.name ?: store.ownerName,
            alreadyOpen = false,
        )
        supportTickets[ticket.id] = ticket
        return ticket
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
            if (product.unlimitedStock) product else
                cart.find { it.productId == product.id }?.let { product.copy(stockMilli = product.stockMilli - it.qtyMilli) } ?: product
        }
        cart.filter { line -> products.firstOrNull { it.id == line.productId }?.unlimitedStock == false }
            .forEach { recordMovement(it.productId, team.firstOrNull { e -> e.id == employeeId }?.name ?: "Doña Rosa") }
        if (paymentMethod == PAYMENT_FIADO && customerId != null) {
            customers = customers.map {
                if (it.id == customerId) it.copy(balanceCents = it.balanceCents + total) else it
            }
            entries.getOrPut(customerId) { mutableListOf() }.add(
                FiadoEntry(nextEntry++, "charge", total, "Venta simulada", now, id,
                    employeeName = team.firstOrNull { it.id == employeeId }?.name)
            )
        }
        return sale
    }

    override suspend fun status(saleId: String): Sale = sales[saleId] ?: error("Venta desconocida")
    override suspend fun cancel(saleId: String): Sale {
        val sale = sales[saleId] ?: error("Venta desconocida")
        if (sale.status == "canceled") return sale
        if (!sale.canCancelPey) throw ApiFailure(409, "El cobro ya no está pendiente")
        products = products.map { product ->
            val line = saleLines[saleId]?.find { it.productId == product.id }
            if (line == null || product.unlimitedStock) product
            else product.copy(stockMilli = product.stockMilli + line.qtyMilli)
        }
        return sale.copy(status = "canceled", qrImage = "", note = "Cancelación SIMULADA. No hubo devolución.")
            .also { sales[saleId] = it }
    }

    override suspend fun adjust(employeeId: Int, productId: Int, deltaMilli: Int, reason: String): Product {
        requireInventoryPermission()
        val current = products.firstOrNull { it.id == productId } ?: throw ApiFailure(404, "Producto desconocido")
        if (current.unlimitedStock) throw ApiFailure(400, "Este producto tiene inventario sin límite")
        val updated = current.copy(stockMilli = current.stockMilli + deltaMilli)
        products = products.map { if (it.id == productId) updated else it }
        recordMovement(productId)
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

    override suspend fun fiadoEntries(customerId: Int): List<FiadoEntry> {
        customers.firstOrNull { it.id == customerId } ?: throw ApiFailure(404, "Cliente desconocido")
        // Igual que el servidor: el historial con nombres exige dueño o canFiado.
        requireFiadoPermission()
        return entries[customerId].orEmpty().sortedByDescending { it.createdAt }
    }

    override suspend fun abono(customerId: Int, amountCents: Long, employeeId: Int, note: String?): Long {
        require(amountCents > 0) { "El abono debe ser mayor a cero" }
        customers.firstOrNull { it.id == customerId } ?: throw ApiFailure(404, "Cliente desconocido")
        requireFiadoPermission()
        val registeredBy = team.firstOrNull { it.id == employeeId }?.name ?: store.ownerName
        val updated = customers.map {
            if (it.id == customerId) it.copy(balanceCents = it.balanceCents - amountCents) else it
        }
        customers = updated
        entries.getOrPut(customerId) { mutableListOf() }.add(
            FiadoEntry(nextEntry++, "payment", amountCents, note, System.currentTimeMillis() / 1000.0,
                employeeName = registeredBy)
        )
        return customers.first { it.id == customerId }.balanceCents
    }

    /** SIMULATED confirmation. Never produces a scannable QR or touches PEY. */
    fun simulatePaid(sale: Sale) {
        val current = sales[sale.id] ?: return
        if (!current.canCancelPey) return
        sales[sale.id] = current.copy(status = "paid_pey", txId = "SIMULADO-SIN-DINERO")
    }

    /** SIMULADO: imita un cobro PEY que el servidor dejó «por conciliar» (sin red ni dinero). */
    fun simulateUnconfirmed(sale: Sale) {
        val current = sales[sale.id] ?: return
        if (current.settled || current.status == "canceled") return
        sales[sale.id] = current.copy(status = "por_conciliar", note = "SIMULADO · el cobro quedó por conciliar")
    }
}

/** Tareas fijas del demo para probar «solo las asignadas» sin red. */
private fun demoTaskSeed(): List<DayTask> {
    val template = demoTemplateTasks("tiendita")
    return listOf(
        DayTask(1, template[0].key, template[0].title, assignedEmployeeId = 2, active = true),
        DayTask(2, template[1].key, template[1].title, assignedEmployeeId = null, active = true),
        DayTask(3, template[2].key, template[2].title, assignedEmployeeId = 3, active = true),
        DayTask(4, template[3].key, template[3].title, assignedEmployeeId = 2, active = false),
    )
}

private fun validateCatalogDraft(draft: CatalogDraft) {
    require(draft.name.isNotBlank()) { "Escribe el nombre del artículo" }
    require(draft.priceCents > 0) { "Escribe un precio mayor a cero" }
    require(PRODUCT_UNITS.contains(draft.unit)) { "Unidad no válida" }
    require(PRODUCT_KINDS.contains(draft.kind)) { "Tipo de artículo no válido" }
    require(imageUrlValid(draft.imageUrl)) { imageUrlProblem(draft.imageUrl) ?: "URL de imagen no válida" }
}

private fun isTodaySeconds(seconds: Double): Boolean {
    if (seconds <= 0.0) return false
    val then = java.util.Calendar.getInstance().apply { timeInMillis = (seconds * 1000).toLong() }
    val now = java.util.Calendar.getInstance()
    return then.get(java.util.Calendar.YEAR) == now.get(java.util.Calendar.YEAR) &&
        then.get(java.util.Calendar.DAY_OF_YEAR) == now.get(java.util.Calendar.DAY_OF_YEAR)
}

internal fun recoverJournal(raw: String?, creating: Boolean): Pair<Sale?, Boolean> {
    if (raw == null) return null to creating
    val sale = runCatching { readSale(JSONObject(raw)) }.getOrNull()
    return sale to (creating || sale == null)
}
