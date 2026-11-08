package mx.abarpay.mobile

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody
import okio.BufferedSink
import java.util.concurrent.TimeUnit

interface ShopRepository {
    suspend fun bootstrap(): Bootstrap
    suspend fun report(): Report
    suspend fun parse(text: String): ParseResult
    suspend fun lookup(code: String): Int
    suspend fun create(employee: Int, cart: List<CartLine>): Sale
    suspend fun status(sale: Sale): Sale
}
class ApiFailure(val code: Int, message: String): Exception(message)
internal fun JSONArray.objects(): List<JSONObject> = (0 until length()).map { getJSONObject(it) }
internal fun JSONObject.nullableString(key: String) = if (isNull(key)) null else optString(key).takeIf { it.isNotBlank() }
internal fun saleJson(s: Sale) = JSONObject().put("saleId", s.id).put("totalCents", s.totalCents)
    .put("chargedCents", s.chargedCents).put("qrImage", s.qrImage).put("expiresAt", s.expiresAt)
    .put("status", s.status).put("txId", s.txId).put("note", s.note)
internal fun readSale(j: JSONObject) = Sale(j.getString("saleId"), j.getLong("totalCents"),
    j.getLong("chargedCents"), j.optString("qrImage"), j.optDouble("expiresAt", 0.0),
    j.optString("status", "pending"), j.nullableString("txId"), j.nullableString("note"))
internal fun saleRequest(employee: Int, lines: List<CartLine>) = JSONObject().put("employeeId", employee)
    .put("items", JSONArray(lines.map { JSONObject().put("productId", it.productId).put("qty", it.qty) }))

/** No PEY or OpenAI credentials, cookies, automatic redirects, or POST retries. */
class ApiRepository(private val base: String): ShopRepository {
    private val client = OkHttpClient.Builder()
        .retryOnConnectionFailure(false)
        .followRedirects(false)
        .followSslRedirects(false)
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(25, TimeUnit.SECONDS)
        .writeTimeout(25, TimeUnit.SECONDS)
        .callTimeout(35, TimeUnit.SECONDS)
        .build()
    private suspend fun request(path: String, body: JSONObject? = null): JSONObject = withContext(Dispatchers.IO) {
        val request = Request.Builder().url(base + path).header("Accept", "application/json")
        if (body != null) {
            val payload = body.toString().toByteArray(Charsets.UTF_8)
            request.post(object : RequestBody() {
                override fun contentType() = "application/json; charset=utf-8".toMediaType()
                override fun contentLength() = payload.size.toLong()
                override fun isOneShot() = true // Also blocks status-based follow-ups such as 503 Retry-After: 0.
                override fun writeTo(sink: BufferedSink) { sink.write(payload) }
            })
        }
        client.newCall(request.build()).execute().use { response ->
            val source = response.body?.source()
            val limit = 4L * 1024 * 1024
            if (source?.request(limit + 1) == true) throw ApiFailure(0, "Respuesta demasiado grande. Conservamos el intento para revisarlo.")
            val raw = source?.readUtf8().orEmpty()
            if (!response.isSuccessful) {
                val detail = runCatching { JSONObject(raw).opt("detail") }.getOrNull()
                throw ApiFailure(response.code, if (detail is String) detail else "El servidor respondió ${response.code}. Revisa los datos y la conexión.")
            }
            JSONObject(raw)
        }
    }
    override suspend fun bootstrap(): Bootstrap {
        val j = request("/api/bootstrap")
        return Bootstrap(j.getString("store"), j.getJSONArray("products").objects().map {
            Product(it.getInt("id"), it.getString("name"), it.getLong("price_cents"), it.getInt("stock"))
        }, j.getJSONArray("employees").objects().map { Employee(it.getInt("id"), it.getString("name"), it.getString("role")) },
            j.getBoolean("modoDemo"), j.getString("ia"))
    }
    override suspend fun report(): Report {
        val j = request("/api/reports/today")
        return Report(j.getLong("totalCents"), j.getLong("chargedCents"), j.getInt("salesCount"), j.getInt("porConciliar"),
            j.getJSONArray("byEmployee").objects().map { it.getString("name") to it.getLong("totalCents") },
            j.getJSONArray("topProducts").objects().map { it.getString("name") to it.getInt("qty") },
            j.getJSONArray("lowStock").objects().map { it.getString("name") to it.getInt("stock") })
    }
    override suspend fun parse(text: String): ParseResult {
        val j = request("/api/cart/parse", JSONObject().put("text", text))
        val unmatched = j.getJSONArray("unmatched")
        return ParseResult(j.getJSONArray("items").objects().map { CartLine(it.getInt("productId"), it.getInt("qty")) },
            (0 until unmatched.length()).map { unmatched.getString(it) }, j.nullableString("warning"))
    }
    override suspend fun lookup(code: String) = request("/api/barcode/lookup", JSONObject().put("code", code)).getInt("productId")
    override suspend fun create(employee: Int, cart: List<CartLine>) = readSale(request("/api/sales", saleRequest(employee, cart)))
    override suspend fun status(sale: Sale): Sale {
        val remote = readSale(request("/api/sales/" + sale.id))
        return remote.copy(qrImage = sale.qrImage, expiresAt = sale.expiresAt)
    }
}

/** Offline UI fixture. Never calls the network or creates a scannable payment QR. */
class DemoRepository: ShopRepository {
    private var products = listOf(Product(1, "Refresco 600 ml", 1800, 36), Product(2, "Papas 45 g", 1500, 28),
        Product(3, "Galletas de vainilla", 1200, 40), Product(4, "Leche entera 1 L", 2700, 4), Product(5, "Agua 1 L", 1400, 22))
    private val paid = mutableMapOf<String, Sale>()
    private val lines = mutableMapOf<String, List<CartLine>>()
    private val sellers = mutableMapOf<String, Int>()
    override suspend fun bootstrap() = Bootstrap("Tiendita de la Esquina", products,
        listOf(Employee(1, "Dueña de ejemplo", "owner"), Employee(2, "Empleado de ejemplo", "employee")), true, "local")
    override suspend fun report(): Report {
        val top = paid.keys.flatMap { lines[it].orEmpty() }.groupBy { it.productId }
            .map { (id, items) -> products.first { it.id == id }.name to items.sumOf { it.qty } }.sortedByDescending { it.second }
        val byPerson = paid.values.groupBy { sellers[it.id] }.map { (id, sales) ->
            (if (id == 1) "Dueña de ejemplo" else "Empleado de ejemplo") to sales.sumOf { it.totalCents }
        }
        return Report(paid.values.sumOf { it.totalCents }, paid.values.sumOf { it.chargedCents }, paid.size, 0,
            byPerson, top, products.filter { it.stock <= 5 }.map { it.name to it.stock })
    }
    override suspend fun parse(text: String): ParseResult {
        val found = products.filter { text.contains(it.name.substringBefore(" "), ignoreCase = true) }
        return ParseResult(found.map { CartLine(it.id, 1) }, if (found.isEmpty()) listOf(text) else emptyList(),
            "SIMULADO: agrega una unidad por nombre encontrado; revisa las cantidades.")
    }
    override suspend fun lookup(code: String) = products.find { code == "DEMO-${it.id}" }?.id
        ?: throw ApiFailure(404, "Código sin enlazar. En simulación prueba DEMO-1.")
    override suspend fun create(employee: Int, cart: List<CartLine>): Sale {
        val sale = Sale("SIMULADO-${java.util.UUID.randomUUID()}", cartEstimate(cart, products), 1,
            expiresAt = System.currentTimeMillis() / 1000.0 + 600)
        lines[sale.id] = cart.toList()
        sellers[sale.id] = employee
        return sale
    }
    override suspend fun status(sale: Sale) = paid[sale.id] ?: sale
    fun simulatePaid(sale: Sale) {
        if (paid.containsKey(sale.id)) return
        paid[sale.id] = sale.copy(status = "paid", txId = "SIMULADO-SIN-DINERO")
        products = products.map { product -> product.copy(stock = product.stock -
            lines[sale.id].orEmpty().filter { it.productId == product.id }.sumOf { it.qty }) }
    }
}

internal fun recoverJournal(raw: String?, creating: Boolean): Pair<Sale?, Boolean> {
    if (raw == null) return null to creating
    val sale = runCatching { readSale(JSONObject(raw)) }.getOrNull()
    return sale to (creating || sale == null)
}
