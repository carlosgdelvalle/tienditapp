package mx.abarpay.mobile

import java.math.BigDecimal
import java.net.URI
import java.text.NumberFormat
import java.util.Locale

const val PAYMENT_CASH = "cash"
const val PAYMENT_PEY = "pey"
const val PAYMENT_FIADO = "fiado"

data class Store(
    val id: String,
    val name: String,
    val businessType: String = "",
    val ownerName: String = "",
)

data class Product(
    val id: Int,
    val name: String,
    val unit: String,
    val priceCents: Long,
    val stockMilli: Int,
    val lowStockMilli: Int = 5000,
    val quick: Boolean = false,
    val unlimitedStock: Boolean = false,
) {
    val isLowStock get() = !unlimitedStock && stockMilli <= lowStockMilli
    val stockLabel get() = if (unlimitedStock) "Sin límite" else qtyText(stockMilli, unit)
}

data class Employee(
    val id: Int,
    val name: String,
    val role: String,
    val nickname: String? = null,
    val active: Boolean = true,
    val canSell: Boolean = true,
    val canFiado: Boolean = true,
    val canInventory: Boolean = false,
) {
    val isOwner get() = role == "owner"
    /** Nombre propio y, si existe, el apodo que la persona eligió al aceptar la invitación. */
    val displayName get() = nickname?.takeIf { it.isNotBlank() }?.let { "$name · $it" } ?: name
}

data class Bootstrap(
    val store: Store,
    val products: List<Product>,
    val employees: List<Employee>,
    val demoMode: Boolean,
    val ai: String = "local",
)

/** Quantities travel in milli-units: 1000 = one piece or one kilogram. */
data class CartLine(val productId: Int, val qtyMilli: Int)

data class ParseLine(
    val productId: Int,
    val name: String,
    val qtyMilli: Int,
    val unit: String,
    val unitPriceCents: Long,
    val lineTotalCents: Long,
)

data class ParseResult(val items: List<ParseLine>, val unmatched: List<String>, val engine: String = "local")

data class EmployeeTotal(val name: String, val totalCents: Long, val salesCount: Int = 0)
data class TopProduct(val name: String, val qtyMilli: Int, val unit: String = "pieza", val productId: Int = 0)
data class StockItem(val name: String, val stockMilli: Int, val unit: String = "pieza")

data class Report(
    val totalCents: Long = 0,
    val collectedCents: Long = 0,
    val cashCents: Long = 0,
    val peyCents: Long = 0,
    val fiadoCents: Long = 0,
    val salesCount: Int = 0,
    val byEmployee: List<EmployeeTotal> = emptyList(),
    val topProducts: List<TopProduct> = emptyList(),
    val lowStock: List<StockItem> = emptyList(),
    val pending: Int = 0,
    val fiadoOutstandingCents: Long = 0,
    val demoMode: Boolean = false,
)

data class Sale(
    val id: String,
    val totalCents: Long,
    val chargedCents: Long,
    val status: String = "pending",
    val paymentMethod: String = PAYMENT_PEY,
    val cashReceivedCents: Long? = null,
    val changeCents: Long? = null,
    val customerId: Int? = null,
    val customerName: String? = null,
    val customerBalanceCents: Long? = null,
    val qrId: String? = null,
    val qrImage: String = "",
    val expiresAt: Double = 0.0,
    val txId: String? = null,
    val note: String? = null,
    val createdAt: Double = 0.0,
) {
    val paid get() = status == "paid_pey" || status == "paid_cash"
    val settled get() = paid || status == "credit"
    val failed get() = status == "failed"
    val unresolved get() = !settled
    val canCancelPey get() = paymentMethod == PAYMENT_PEY && status in setOf("pending", "por_conciliar", "expired")
}

data class Customer(val id: Int, val name: String, val phone: String? = null, val balanceCents: Long = 0)

data class FiadoEntry(
    val id: Int,
    val kind: String,
    val amountCents: Long,
    val note: String? = null,
    val createdAt: Double = 0.0,
    val saleId: String? = null,
)

data class CustomerDetail(val customer: Customer, val entries: List<FiadoEntry> = emptyList())

fun money(cents: Long): String = NumberFormat.getCurrencyInstance(Locale.forLanguageTag("es-MX"))
    .format(BigDecimal.valueOf(cents, 2))

/** 1000 milli = one piece or one kilogram. 500 milli prints as 0.5 kg. */
fun qtyText(qtyMilli: Int, unit: String): String {
    val sign = if (qtyMilli < 0) "-" else ""
    val abs = kotlin.math.abs(qtyMilli)
    val whole = abs / 1000
    val rem = abs % 1000
    val number = if (rem == 0) "$sign$whole" else {
        val frac = rem.toString().padStart(3, '0').trimEnd('0')
        "$sign$whole.$frac"
    }
    return if (unit == "kg") "$number kg" else "$number pza"
}

/** Mirrors the server formula: lineTotalCents = round(unitPriceCents * qtyMilli / 1000). */
fun lineTotalCents(unitPriceCents: Long, qtyMilli: Int): Long =
    Math.floorDiv(unitPriceCents * qtyMilli.toLong() + 500L, 1000L)

fun changeQuantity(cart: List<CartLine>, id: Int, deltaMilli: Int): List<CartLine> {
    val next = (cart.find { it.productId == id }?.qtyMilli ?: 0) + deltaMilli
    require(next in 0..999_000) { "Usa cantidades entre 0 y 999 unidades" }
    return cart.filterNot { it.productId == id } + if (next == 0) emptyList() else listOf(CartLine(id, next))
}

/** One-tap decrement never sends a half-kilo line below zero. */
fun decrementStep(qtyMilli: Int): Int = -minOf(1000, qtyMilli)

fun cartEstimate(cart: List<CartLine>, products: List<Product>): Long = cart.sumOf { line ->
    val product = products.firstOrNull { it.id == line.productId } ?: error("Actualiza el catálogo")
    lineTotalCents(product.priceCents, line.qtyMilli)
}

/** Parses "100", "100.50", "1,234.50" or "$250" into integer cents. Null when unusable. */
fun parseCashCents(raw: String): Long? {
    val cleaned = raw.trim().replace("\u0024", "").replace(" ", "")
    if (cleaned.isEmpty()) return null
    val normalized = when {
        cleaned.contains('.') -> cleaned.replace(",", "")
        cleaned.count { it == ',' } == 1 && cleaned.substringAfter(',').length <= 2 -> cleaned.replace(',', '.')
        else -> cleaned.replace(",", "")
    }
    if (!normalized.matches(Regex("^\\d{1,9}(\\.\\d{1,2})?\u0024"))) return null
    val parts = normalized.split('.')
    val pesos = parts[0].toLongOrNull() ?: return null
    val cents = if (parts.size > 1) parts[1].padEnd(2, '0').toLongOrNull() ?: return null else 0L
    return pesos * 100 + cents
}

/** Only HTTPS, except the emulator host in debug builds. */
fun normalizeServer(input: String, debug: Boolean): String {
    val uri = URI(input.trim())
    require(uri.host != null && uri.userInfo == null && uri.rawQuery == null && uri.rawFragment == null &&
        (uri.path.isNullOrBlank() || uri.path == "/")) { "Usa la dirección raíz del servidor, sin claves ni rutas" }
    require(uri.scheme == "https" || (debug && uri.scheme == "http" && uri.host == "10.0.2.2")) {
        "Usa HTTPS. En debug se permite http://10.0.2.2:8000 para el emulador."
    }
    return input.trim().trimEnd('/')
}

/** Unknown HTTP/transport results MUST NOT automatically create another sale. */
fun definitelyRejected(code: Int) = code in setOf(400, 401, 403, 404, 422)

/** The QR only makes sense while a PEY sale is pending and has not expired. */
fun canDisplayQr(sale: Sale, nowSeconds: Double, hidden: Boolean): Boolean =
    !hidden && sale.paymentMethod == PAYMENT_PEY && sale.status == "pending" && sale.expiresAt > nowSeconds

fun methodLabel(method: String): String = when (method) {
    PAYMENT_CASH -> "Efectivo"
    PAYMENT_FIADO -> "Fiado"
    else -> "PEY / CoDi"
}

fun statusLabel(status: String): String = when (status) {
    "paid_cash" -> "Pagada en efectivo"
    "paid_pey" -> "Pagada con PEY"
    "credit" -> "A crédito (fiado)"
    "pending" -> "Pendiente de pago"
    "por_conciliar" -> "Por conciliar"
    "failed" -> "Pago fallido"
    "canceled" -> "Cancelada"
    "expired" -> "Vencida"
    else -> status
}

// ---------------------------------------------------------------------------
// Offline demo parser (simulation mode only; the real parser lives on the server)
// ---------------------------------------------------------------------------

private val numberWords = mapOf(
    "un" to 1000, "una" to 1000, "uno" to 1000, "dos" to 2000, "tres" to 3000,
    "cuatro" to 4000, "cinco" to 5000, "seis" to 6000, "siete" to 7000,
    "ocho" to 8000, "nueve" to 9000, "diez" to 10000,
)

/** Small local parser so the offline demo still understands typical dictation. */
fun demoParse(text: String, products: List<Product>): ParseResult {
    val items = mutableListOf<ParseLine>()
    val unmatched = mutableListOf<String>()
    text.split(Regex("(?:\\s+y\\s+|,|;|\\s+con\\s+)")).map { it.trim() }.filter { it.isNotEmpty() }.forEach { chunk ->
        val normalized = chunk.lowercase(Locale.ROOT)
        val product = products.firstOrNull { matchesProduct(normalized, it) }
        if (product == null) {
            unmatched += chunk
        } else {
            val qty = qtyFrom(normalized)
            val existing = items.indexOfFirst { it.productId == product.id }
            if (existing >= 0) {
                val merged = items[existing].qtyMilli + qty
                items[existing] = items[existing].copy(qtyMilli = merged, lineTotalCents = lineTotalCents(product.priceCents, merged))
            } else {
                items += ParseLine(product.id, product.name, qty, product.unit, product.priceCents,
                    lineTotalCents(product.priceCents, qty))
            }
        }
    }
    return ParseResult(items, unmatched, "demo")
}

private fun matchesProduct(chunk: String, product: Product): Boolean {
    val base = product.name.substringBefore(" (").lowercase(Locale.ROOT)
    if (chunk.contains(base)) return true
    val token = base.split(' ', '-').firstOrNull { it.length >= 3 } ?: return false
    return chunk.contains(token)
}

private fun qtyFrom(chunk: String): Int {
    Regex("(\\d+(?:[.,]\\d+)?)\\s*(kg|kilos?|kilogramos?)").find(chunk)?.let {
        return (it.groupValues[1].replace(',', '.').toDouble() * 1000).toInt()
    }
    Regex("(\\d+(?:[.,]\\d+)?)\\s*(g|gr|gramos?)").find(chunk)?.let {
        return it.groupValues[1].replace(',', '.').toDouble().toInt()
    }
    Regex("(\\d+)\\s*/\\s*(\\d+)").find(chunk)?.let {
        val numerator = it.groupValues[1].toDouble()
        val denominator = it.groupValues[2].toDouble()
        if (denominator > 0) return ((numerator / denominator) * 1000).toInt()
    }
    if (chunk.contains("tres cuartos")) return 750
    if (chunk.contains("medio") || chunk.contains("media")) return 500
    if (chunk.contains("un cuarto") || chunk.contains("cuarto de")) return 250
    Regex("(\\d+)\\s*(piezas?|pza|pzas)?").find(chunk)?.let {
        val value = it.groupValues[1].toInt()
        return if (value in 0..999) value * 1000 else 1000
    }
    chunk.split(' ', ',', '.').firstOrNull { numberWords.containsKey(it) }?.let { return numberWords.getValue(it) }
    return 1000
}

// ---------------------------------------------------------------------------
// Contrato v2 · onboarding, equipo, permisos e inventario
// ---------------------------------------------------------------------------

const val TAB_HOME = "Inicio"
const val TAB_SELL = "Cobrar"
const val TAB_FIADO = "Fiado"
const val TAB_INVENTORY = "Inventario"
const val TAB_REPORTS = "Reportes"

/** Metas del onboarding: chips multi-select. Se guardan solo en este teléfono. */
val OWNER_GOALS = listOf(
    "Organizar mis ventas y gastos",
    "Controlar lo que me deben",
    "Gestionar mejor mi inventario",
    "Ver estadísticas avanzadas",
)

/** Tipos de negocio del onboarding: chips de una sola elección. */
val BUSINESS_TYPES = listOf("Tiendita", "Abarrotes", "Miscelánea", "Fondita", "Otro")

data class StoreProfile(
    val storeId: String = "",
    val name: String = "",
    val businessType: String = "",
    val ownerName: String = "",
)

data class Invite(val token: String, val employeeId: Int, val url: String)

data class InviteInfo(
    val token: String,
    val employeeId: Int,
    val name: String,
    val storeName: String,
    val businessType: String,
    val canSell: Boolean = true,
    val canFiado: Boolean = true,
    val canInventory: Boolean = false,
)

/** Una línea que el servidor entendió del dictado. qtyMilli nulo = falta la cantidad. */
data class VoiceLine(
    val productId: Int,
    val name: String,
    val qtyMilli: Int?,
    val unit: String = "pieza",
)

data class VoiceResult(val items: List<VoiceLine> = emptyList(), val note: String? = null)

data class InventoryItem(
    val productId: Int,
    val name: String,
    val unit: String = "pieza",
    val stockMilli: Int = 0,
    val unlimitedStock: Boolean = false,
    val lastUpdatedAt: Double? = null,
    val lastUpdatedByName: String? = null,
    val lastUpdatedByNickname: String? = null,
)

data class InventorySnapshot(val items: List<InventoryItem> = emptyList(), val totalValueCents: Long = 0)

/** Pestañas visibles según rol y permisos. El dueño siempre puede vender e inventario. Sin perfil se muestran todas. */
fun tabsFor(employee: Employee?): List<String> = tabsFor(
    role = employee?.role ?: "owner",
    canSell = (employee?.canSell ?: true) || employee?.role == "owner",
    canInventory = (employee?.canInventory ?: true) || employee?.role == "owner",
)

fun tabsFor(role: String, canSell: Boolean, canInventory: Boolean): List<String> = buildList {
    add(TAB_HOME)
    if (canSell) add(TAB_SELL)
    add(TAB_FIADO)
    if (canInventory) add(TAB_INVENTORY)
    if (role == "owner") add(TAB_REPORTS)
}

fun canUseTabs(employee: Employee?, tab: String): Boolean = tab in tabsFor(employee)

fun canChoosePaymentMethod(employee: Employee?, method: String): Boolean =
    method != PAYMENT_FIADO || employee == null || employee.canFiado

fun canUseInventory(employee: Employee?): Boolean = employee == null || employee.canInventory || employee.role == "owner"

fun canUseReports(employee: Employee?): Boolean = employee == null || employee.role == "owner"

/** Solo los empleados inactivos con invitación pendiente cuentan como invitación por aceptar. */
fun pendingInvites(team: List<Employee>?): Int =
    team?.count { !it.active && it.role != "owner" } ?: 0

fun onboardingReady(ownerName: String, storeName: String, businessType: String): Boolean =
    ownerName.isNotBlank() && storeName.isNotBlank() && businessType.isNotBlank()

fun goalSelectionLabel(goals: List<String>): String =
    if (goals.isEmpty()) "Sin metas por ahora" else goals.joinToString(", ")

/**
 * Acepta abarpay://empleado/<token> y https://<host>/invite/<token>.
 * Devuelve null si el enlace no trae un token válido.
 */
fun extractInviteToken(raw: String?): String? {
    if (raw.isNullOrBlank()) return null
    val uri = runCatching { URI(raw.trim()) }.getOrNull() ?: return null
    val token = when {
        uri.scheme == "abarpay" && uri.host == "empleado" -> uri.path?.trim('/')
        uri.scheme == "https" && uri.path?.startsWith("/invite/") == true ->
            uri.path.removePrefix("/invite/").trim('/')
        else -> null
    }
    return token?.takeIf { it.matches(Regex("^[A-Za-z0-9-]{4,128}$")) }
}

/** 12 -> 12000 (12 piezas); 1.5 -> 1500 (1.5 kg). Null si no se puede leer. */
fun parseQtyMilli(raw: String): Int? {
    val cents = parseCashCents(raw) ?: return null
    val milli = cents * 10L
    return if (milli in 0L..999_000L) milli.toInt() else null
}

/** Texto editable para la hoja de confirmación: 12000 -> "12", 1500 -> "1.5". */
fun qtyInputText(qtyMilli: Int): String {
    val whole = qtyMilli / 1000
    val rem = qtyMilli % 1000
    return if (rem == 0) whole.toString()
    else String.format(Locale.ROOT, "%.3f", qtyMilli / 1000.0).trimEnd('0').trimEnd('.')
}

fun voiceLineLabel(line: VoiceLine): String =
    line.name + ": " + (line.qtyMilli?.let { qtyText(it, line.unit) } ?: "falta la cantidad")

fun voiceSummary(items: List<VoiceLine>): String =
    items.joinToString(", ") { voiceLineLabel(it) }

/** Ajustes recientes para «Actividades»: los productos con movimiento más nuevo primero. */
fun recentAdjustments(snapshot: InventorySnapshot?, limit: Int = 3): List<InventoryItem> =
    snapshot?.items.orEmpty()
        .filter { it.lastUpdatedAt != null }
        .sortedByDescending { it.lastUpdatedAt ?: 0.0 }
        .take(limit)

// ---------------------------------------------------------------------------
// Contrato v2 · tickets de soporte (cobros PEY que quedaron por conciliar)
// ---------------------------------------------------------------------------

/**
 * Ticket que el servidor guarda cuando un cobro quedó en el limbo. Todos los
 * campos son defensivos: si el servidor no manda alguno, el teléfono no truena.
 * [id] llega como `tkt_<hex>` y es el folio que también se ve en la consola.
 */
data class SupportTicket(
    val id: String = "",
    val saleId: String? = null,
    val saleStatus: String? = null,
    val saleTotalCents: Long = 0,
    val chargedCents: Long = 0,
    val peyTxId: String? = null,
    val note: String? = null,
    val status: String = "open",
    val createdAt: Double = 0.0,
    val reportedByName: String? = null,
    val alreadyOpen: Boolean = false,
) {
    val open get() = status == "open"
}

/**
 * El ticket aparece solo en un cobro PEY que quedó «por conciliar» y no está
 * asentado. Expired/canceled/failed siguen siendo estados normales sin acción.
 */
fun canReportTicket(sale: Sale): Boolean =
    sale.paymentMethod == PAYMENT_PEY && !sale.settled && sale.status == "por_conciliar"

/** Mensaje del teléfono: «Ticket #… creado» o «Ya existe el ticket #…». */
fun ticketMessage(ticket: SupportTicket): String =
    if (ticket.alreadyOpen) "Ya existe el ticket #" + ticket.id
    else "Ticket #" + ticket.id + " creado"
