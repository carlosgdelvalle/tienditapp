package mx.abarpay.mobile

import java.net.URI
import java.text.NumberFormat
import java.util.Locale

data class Product(val id: Int, val name: String, val priceCents: Long, val stock: Int)
data class Employee(val id: Int, val name: String, val role: String)
data class Bootstrap(val store: String, val products: List<Product>, val employees: List<Employee>, val demoCharge: Boolean, val ai: String)
data class CartLine(val productId: Int, val qty: Int)
data class ParseResult(val items: List<CartLine>, val unmatched: List<String>, val warning: String?)
data class Report(val totalCents: Long, val chargedCents: Long, val salesCount: Int, val pending: Int,
    val employees: List<Pair<String, Long>>, val top: List<Pair<String, Int>>, val lowStock: List<Pair<String, Int>>)
data class Sale(val id: String, val totalCents: Long, val chargedCents: Long, val qrImage: String = "",
    val expiresAt: Double = 0.0, val status: String = "pending", val txId: String? = null, val note: String? = null) {
    val paid get() = status == "paid"
    val unresolved get() = !paid // Even expired can receive a late payment. Keep the reference.
}

fun money(cents: Long): String = NumberFormat.getCurrencyInstance(Locale.forLanguageTag("es-MX"))
    .format(java.math.BigDecimal.valueOf(cents, 2))

fun changeQuantity(cart: List<CartLine>, id: Int, delta: Int): List<CartLine> {
    val next = (cart.find { it.productId == id }?.qty ?: 0).toLong() + delta.toLong()
    require(next in 0..999) { "Usa cantidades entre 0 y 999" }
    return cart.filterNot { it.productId == id } + if (next == 0L) emptyList() else listOf(CartLine(id, next.toInt()))
}
fun cartEstimate(cart: List<CartLine>, products: List<Product>): Long = cart.sumOf { line ->
    val product = products.firstOrNull { it.id == line.productId } ?: error("Actualiza el catálogo")
    Math.multiplyExact(product.priceCents, line.qty.toLong())
}

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
fun definitelyRejected(code: Int) = code in setOf(400, 401, 403, 422)

fun canDisplayQr(sale: Sale, nowSeconds: Double, hidden: Boolean): Boolean =
    !hidden && sale.status == "pending" && sale.expiresAt > nowSeconds
