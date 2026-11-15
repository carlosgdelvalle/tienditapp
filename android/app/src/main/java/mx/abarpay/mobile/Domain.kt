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
    // Contrato v3 · catálogo generalizado: tipo de artículo, categoría, duración y alias.
    val kind: String = KIND_PRODUCTO,
    val category: String? = null,
    val durationMinutes: Int? = null,
    val aliases: List<String> = emptyList(),
) {
    val isLowStock get() = !unlimitedStock && stockMilli <= lowStockMilli
    val stockLabel get() = if (unlimitedStock) "Sin límite" else qtyText(stockMilli, unit)
    /** Servicios y platillos no llevan inventario: nunca muestran controles de stock. */
    val tracksStock get() = kind == KIND_PRODUCTO && !unlimitedStock
    /** Etiqueta del catálogo/venta: «24 unidades disponibles» o «Sin límite». */
    val availableLabel get() = when {
        !tracksStock -> "Sin límite"
        unit == "pieza" && stockMilli == 1000 -> "1 unidad disponible"
        unit == "pieza" -> qtyNumber(stockMilli) + " unidades disponibles"
        else -> qtyText(stockMilli, unit) + " disponibles"
    }
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
    // Contrato v3 · gastos del día (botón «Registrar gasto»).
    val totalExpensesCents: Long = 0,
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
fun qtyText(qtyMilli: Int, unit: String): String = qtyNumber(qtyMilli) + " " + unitLabel(unit)

/** Solo el número de la cantidad (sin unidad): 12000 -> "12", 1500 -> "1.5". */
fun qtyNumber(qtyMilli: Int): String {
    val sign = if (qtyMilli < 0) "-" else ""
    val abs = kotlin.math.abs(qtyMilli)
    val whole = abs / 1000
    val rem = abs % 1000
    return if (rem == 0) "$sign$whole" else {
        val frac = rem.toString().padStart(3, '0').trimEnd('0')
        "$sign$whole.$frac"
    }
}

/** Etiqueta corta de la unidad para badges y textos. */
fun unitLabel(unit: String): String = when (unit) {
    "pieza" -> "pza"
    "kg" -> "kg"
    "g" -> "g"
    "litro" -> "L"
    "servicio" -> "servicio"
    "sesion" -> "sesión"
    "turno" -> "turno"
    "minuto" -> "min"
    "hora" -> "hora"
    "paquete" -> "paquete"
    "combo" -> "combo"
    else -> unit.ifBlank { "pza" }
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
fun decrementStep(qtyMilli: Int, step: Int = 1000): Int = -minOf(step, qtyMilli)

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

/**
 * Tipos de negocio del onboarding v3: chips de una sola elección.
 * [BusinessTypeOption.key] es el valor que acepta POST /api/catalog/templates/apply.
 * Miscelánea usa la plantilla genérica ("otro") porque el contrato del servidor
 * solo define tiendita, tortilleria, taqueria, comida-corrida, peluqueria,
 * estetica, fondita y otro.
 */
data class BusinessTypeOption(val label: String, val key: String)

val BUSINESS_TYPES = listOf(
    BusinessTypeOption("Tiendita/Abarrotes", "tiendita"),
    BusinessTypeOption("Miscelánea", "miscelanea"),
    BusinessTypeOption("Tortillería", "tortilleria"),
    BusinessTypeOption("Taquería", "taqueria"),
    BusinessTypeOption("Comida corrida", "comida-corrida"),
    BusinessTypeOption("Peluquería/Barbería", "peluqueria"),
    BusinessTypeOption("Estética de uñas", "estetica"),
    BusinessTypeOption("Fondita", "fondita"),
    BusinessTypeOption("Otro", "otro"),
)

val BUSINESS_TYPE_LABELS: List<String> = BUSINESS_TYPES.map { it.label }

/** Tipo de negocio → plantilla que entiende el servidor (Miscelánea → «otro»). */
fun templateBusinessType(businessType: String): String {
    val key = BUSINESS_TYPES.firstOrNull { it.label == businessType || it.key == businessType }?.key
        ?: return "otro"
    // Miscelánea no está en el enum del servidor: usa la plantilla genérica.
    return if (key == "miscelanea") "otro" else key
}

/** Paso «¿Qué vendes?»: multi-select guardado en las preferencias del teléfono. */
data class SellsOption(val label: String, val key: String)

val SELLS_OPTIONS = listOf(
    SellsOption("Productos", "productos"),
    SellsOption("Servicios", "servicios"),
    SellsOption("Comida preparada y bebidas", "comida"),
)

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


// ---------------------------------------------------------------------------
// Contrato v3 · catálogo generalizado, tareas, gastos y comprobante
// ---------------------------------------------------------------------------

const val KIND_PRODUCTO = "producto"
const val KIND_SERVICIO = "servicio"
const val KIND_PLATILLO = "platillo"

val PRODUCT_KINDS = listOf(KIND_PRODUCTO, KIND_SERVICIO, KIND_PLATILLO)

/** Unidades que acepta POST/PATCH /api/catalog (CHECK ampliado del contrato v3). */
val PRODUCT_UNITS = listOf(
    "pieza", "kg", "g", "litro", "servicio", "sesion", "turno",
    "minuto", "hora", "paquete", "combo",
)

fun kindLabel(kind: String): String = when (kind) {
    KIND_SERVICIO -> "Servicio"
    KIND_PLATILLO -> "Platillo"
    else -> "Producto"
}

fun catalogUnitLabel(unit: String): String = unitLabel(unit)

/** Los servicios y platillos no llevan inventario ni controles de stock. */
fun kindTracksStock(kind: String): Boolean = kind == KIND_PRODUCTO

/** Copy v3: «Tu negocio» (nunca «Tu tiendita») y «Inventario bajo» (no «Stock bajo»). */
const val COPY_HOME_TITLE = "Tu negocio"
const val COPY_LOW_STOCK = "Inventario bajo"

fun stockBadge(product: Product): String = product.availableLabel

/**
 * Presets de cantidad por unidad, en mili-unidades (1000 = 1 unidad).
 * servicio/sesión/turno/combo → 1,2,3; kg → 250g/500g/1kg/2kg;
 * minuto → 30/60/90. pieza/g/paquete usan botones +1/−1.
 */
val QUANTITY_PRESETS: Map<String, List<Int>> = mapOf(
    "servicio" to listOf(1000, 2000, 3000),
    "sesion" to listOf(1000, 2000, 3000),
    "turno" to listOf(1000, 2000, 3000),
    "combo" to listOf(1000, 2000, 3000),
    "kg" to listOf(250, 500, 1000, 2000),
    "minuto" to listOf(30_000, 60_000, 90_000),
)

fun quantityPresets(unit: String): List<Int>? = QUANTITY_PRESETS[unit]

/** Tamaño de un toque de +/−: siempre una unidad (1000 milli = 1 pieza, g, kg, paquete…). */
fun quantityStep(unit: String): Int {
    require(unit.isNotBlank()) { "Unidad vacía" }
    return 1000
}

/**
 * Etiqueta del preset: en kg los cuartos se muestran como gramos
 * (250 g, 500 g, 1 kg, 2 kg), como pide el contrato v3.
 */
fun quantityPresetLabel(qtyMilli: Int, unit: String): String =
    if (unit == "kg" && qtyMilli in 1..999) qtyMilli.toString() + " g" else qtyText(qtyMilli, unit)

/** Página del catálogo: el servidor puede paginar y la app filtra en local. */
data class CatalogPage(val items: List<Product> = emptyList(), val total: Int = 0)

/** Formulario de alta/edición del catálogo (contrato v3). */
data class CatalogDraft(
    val name: String = "",
    val unit: String = "pieza",
    val priceCents: Long = 0,
    val aliases: List<String> = emptyList(),
    val stockMilli: Int? = null,
    val unlimitedStock: Boolean = false,
    val kind: String = KIND_PRODUCTO,
    val category: String? = null,
    val durationMinutes: Int? = null,
    val quick: Boolean = false,
) {
    val tracksStock get() = kindTracksStock(kind) && !unlimitedStock
}

fun catalogDraft(product: Product): CatalogDraft = CatalogDraft(
    name = product.name,
    unit = product.unit,
    priceCents = product.priceCents,
    aliases = product.aliases,
    stockMilli = product.stockMilli,
    unlimitedStock = product.unlimitedStock || !kindTracksStock(product.kind),
    kind = product.kind,
    category = product.category,
    durationMinutes = product.durationMinutes,
    quick = product.quick,
)

/** Nombre y precio son obligatorios; el resto tiene valores sensatos. */
fun catalogDraftReady(draft: CatalogDraft): Boolean = draft.name.isNotBlank() && draft.priceCents > 0

fun aliasesFrom(raw: String): List<String> =
    raw.split(',', ';').map { it.trim() }.filter { it.isNotBlank() }.distinct()

fun aliasesText(aliases: List<String>): String = aliases.joinToString(", ")

fun catalogCategories(products: List<Product>): List<String> =
    products.mapNotNull { it.category?.takeIf { c -> c.isNotBlank() } }
        .distinct().sortedBy { it.lowercase() }

fun catalogMatches(product: Product, query: String, category: String?, kind: String?): Boolean {
    if (category != null && product.category != category) return false
    if (kind != null && product.kind != kind) return false
    val q = query.trim().lowercase()
    if (q.isBlank()) return true
    return product.name.lowercase().contains(q) || product.aliases.any { it.lowercase().contains(q) }
}

/** Rápidos primero y luego por nombre: el catálogo grande se ordena en la app. */
fun sortedCatalog(products: List<Product>): List<Product> =
    products.sortedWith(compareByDescending<Product> { it.quick }.thenBy { it.name.lowercase() })

fun catalogItemSubtitle(product: Product): String = buildList {
    add(kindLabel(product.kind) + " · " + money(product.priceCents) + " · " + unitLabel(product.unit))
    product.category?.takeIf { it.isNotBlank() }?.let { add(it) }
    if (product.tracksStock) add(qtyText(product.stockMilli, product.unit) + " disponibles")
    product.durationMinutes?.let { add(it.toString() + " min") }
}.joinToString(" · ")

internal fun catalogCompare(a: Product, b: Product): Int = a.name.compareTo(b.name, ignoreCase = true)

// --- Tareas del día ---------------------------------------------------------

/** Tarea fija del tipo de negocio; solo se muestra si está asignada y activa. */
data class DayTask(
    val id: Int,
    val key: String = "",
    val title: String = "",
    val assignedEmployeeId: Int? = null,
    val active: Boolean = true,
) {
    val assigned get() = assignedEmployeeId != null
}

/** Un empleado SOLO ve sus tareas asignadas y activas; el dueño ve todas. */
fun tasksFor(tasks: List<DayTask>?, employee: Employee?): List<DayTask> {
    val all = tasks.orEmpty()
    if (employee == null || employee.isOwner) return all
    return all.filter { it.active && it.assignedEmployeeId == employee.id }
}

fun taskAssigneeName(task: DayTask, team: List<Employee>?): String =
    team?.firstOrNull { it.id == task.assignedEmployeeId }?.displayName ?: "Sin asignar"

fun assignableEmployees(team: List<Employee>?): List<Employee> =
    team.orEmpty().filter { it.active && !it.isOwner }

// --- Gastos -----------------------------------------------------------------

data class Expense(
    val id: Int,
    val amountCents: Long,
    val note: String? = null,
    val createdAt: Double = 0.0,
    val employeeId: Int? = null,
    val employeeName: String? = null,
)

/** Resultado del dictado de gastos; amountCents = 0 significa «no entendí el monto». */
data class ExpenseDraft(val amountCents: Long = 0, val note: String? = null)

fun expenseReady(amountCents: Long?): Boolean = (amountCents ?: 0) > 0

fun expenseLabel(expense: Expense): String {
    val note = expense.note?.takeIf { it.isNotBlank() }
    return money(expense.amountCents) + (note?.let { " · " + it } ?: "")
}

fun expenseRegisteredMessage(amountCents: Long, note: String?): String {
    val cleanNote = note?.trim()?.takeIf { it.isNotBlank() }
    return "Gasto registrado: " + money(amountCents) + (cleanNote?.let { " · " + it } ?: "")
}

fun expenseVoiceMessage(draft: ExpenseDraft): String {
    if (draft.amountCents <= 0) return draft.note ?: "No entendí el monto. Escríbelo a mano."
    val note = draft.note?.takeIf { it.isNotBlank() }
    return "Entendí: " + money(draft.amountCents) + (note?.let { " · " + it } ?: "")
}

private val expenseNumberWords = mapOf(
    "un" to 100L, "uno" to 100L, "una" to 100L, "dos" to 200L, "tres" to 300L,
    "cuatro" to 400L, "cinco" to 500L, "seis" to 600L, "siete" to 700L,
    "ocho" to 800L, "nueve" to 900L, "diez" to 1000L, "once" to 1100L,
    "doce" to 1200L, "trece" to 1300L, "catorce" to 1400L, "quince" to 1500L,
    "dieciseis" to 1600L, "dieciséis" to 1600L, "diecisiete" to 1700L,
    "dieciocho" to 1800L, "diecinueve" to 1900L, "veinte" to 2000L,
    "treinta" to 3000L, "cuarenta" to 4000L, "cincuenta" to 5000L,
    "sesenta" to 6000L, "setenta" to 7000L, "ochenta" to 8000L,
    "noventa" to 9000L, "cien" to 10000L, "ciento" to 10000L,
    "doscientos" to 20000L, "trescientos" to 30000L, "cuatrocientos" to 40000L,
    "quinientos" to 50000L, "seiscientos" to 60000L, "setecientos" to 70000L,
    "ochocientos" to 80000L, "novecientos" to 90000L, "mil" to 100000L,
)

private val expenseStopWords = setOf(
    "pesos", "peso", "de", "del", "en", "para", "por", "el", "la", "los", "las",
    "un", "una", "gaste", "gasté", "gasto", "compre", "compré", "pague", "pagué",
    "fue", "son", "es", "y", "con", "a",
)

/**
 * Parser LOCAL del dictado de gastos (simulación sin red). En API el servidor
 * manda: POST /api/expenses/voice. «veinte pesos de gas» → 2000, nota «gas».
 */
fun parseExpenseVoice(text: String): ExpenseDraft? {
    val clean = text.trim().lowercase(Locale.ROOT)
    if (clean.isBlank()) return null
    val digits = Regex("(\\d{1,7}(?:[.,]\\d{1,2})?)").find(clean)?.groupValues?.get(1)
    val amountCents = if (digits != null) {
        parseCashCents(digits)
    } else {
        val words = clean.split(Regex("[^a-záéíóúüñ]+")).filter { it.isNotBlank() }
        // «veinte» o «ciento cincuenta»: se suman los números seguidos.
        var total = 0L
        var found = false
        for (word in words) {
            val value = expenseNumberWords[word] ?: continue
            total += value
            found = true
        }
        if (found) total else null
    } ?: return null
    if (amountCents <= 0) return null
    val noteWords = clean.split(Regex("[^a-záéíóúüñ0-9]+"))
        .filter { it.isNotBlank() && !expenseStopWords.contains(it) && !it.all { ch -> ch.isDigit() } &&
            expenseNumberWords[it] == null && !it.matches(Regex("\\d+[.,]?\\d*")) }
    val note = noteWords.joinToString(" ").trim().takeIf { it.isNotBlank() }
    return ExpenseDraft(amountCents, note)
}

// --- Comprobante ------------------------------------------------------------

data class ReceiptLine(val label: String, val value: String)

/** Filas del comprobante que se comparte como imagen o PDF. */
fun receiptRows(storeName: String, sale: Sale): List<ReceiptLine> = buildList {
    add(ReceiptLine("Negocio", storeName.ifBlank { "Mi negocio" }))
    add(ReceiptLine("Venta", sale.id))
    add(ReceiptLine("Forma de pago", methodLabel(sale.paymentMethod)))
    add(ReceiptLine("Estado", statusLabel(sale.status)))
    add(ReceiptLine("Total", money(sale.totalCents)))
    if (sale.paymentMethod == PAYMENT_PEY && sale.chargedCents != sale.totalCents) {
        add(ReceiptLine("Monto cobrado", money(sale.chargedCents)))
    }
    if (sale.paymentMethod == PAYMENT_CASH) {
        sale.cashReceivedCents?.let { add(ReceiptLine("Recibido", money(it))) }
        sale.changeCents?.let { add(ReceiptLine("Cambio", money(it))) }
    }
    sale.customerName?.let { add(ReceiptLine("Cliente", it)) }
    sale.txId?.let { add(ReceiptLine("Folio PEY", it)) }
    sale.note?.takeIf { it.isNotBlank() }?.let { add(ReceiptLine("Nota", it)) }
}

fun receiptHeadline(sale: Sale): String = "Comprobante de venta"

/** Solo las ventas asentadas (efectivo, fiado o PEY pagada) se comparten. */
fun canShareReceipt(sale: Sale): Boolean = sale.settled

fun receiptFileName(sale: Sale): String =
    "comprobante-" + sale.id.replace(Regex("[^A-Za-z0-9_-]"), "_")


/** Texto editable del monto en pesos: 2000 → "20", 2050 → "20.50". */
fun cashInputText(cents: Long): String {
    val pesos = cents / 100
    val resto = (cents % 100).toInt()
    return if (resto == 0) pesos.toString() else String.format(Locale.ROOT, "%d.%02d", pesos, resto)
}
