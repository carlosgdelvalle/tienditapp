package mx.abarpay.mobile

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class ShopState(
    val simulated: Boolean = true,
    val server: String = "",
    val bootstrap: Bootstrap? = null,
    val employee: Employee? = null,
    val report: Report? = null,
    val cart: List<CartLine> = emptyList(),
    val paymentMethod: String = PAYMENT_CASH,
    val customer: Customer? = null,
    val customers: List<Customer> = emptyList(),
    val customerDetail: CustomerDetail? = null,
    val sale: Sale? = null,
    val uncertain: Boolean = false,
    val busy: Boolean = false,
    val message: String? = null,
    val tab: String = "Inicio",
    val qrHidden: Boolean = false,
    val linkCode: String? = null,
)

class ShopViewModel(app: Application) : AndroidViewModel(app) {
    private val prefs = app.getSharedPreferences("development_session", 0)
    private var repo: ShopRepository = DemoRepository()
    private val state: MutableStateFlow<ShopState>
    val ui: kotlinx.coroutines.flow.StateFlow<ShopState>
    private var checking = false

    init {
        // Release: servidor de demo fijo y sin configuración manual. Debug: conserva
        // el servidor guardado o el modo simulación para las pruebas locales.
        val server = if (BuildConfig.DEBUG) prefs.getString("server", "").orEmpty() else BuildConfig.DEMO_SERVER
        val (sale, uncertain) = recoverJournal(prefs.getString("sale", null), prefs.getBoolean("creating", false))
        state = MutableStateFlow(
            when {
                server.isNotBlank() -> ShopState(
                    simulated = false, server = server, sale = sale, uncertain = uncertain,
                    qrHidden = prefs.getBoolean("qrHidden", false),
                )
                sale != null || uncertain -> ShopState(
                    simulated = false, sale = sale, uncertain = true,
                    message = "No se pudo recuperar la conexión del cobro. No generes otro intento.",
                )
                else -> ShopState()
            }
        )
        ui = state.asStateFlow()
        if (server.isNotBlank()) repo = ApiRepository(server)
        if (server.isNotBlank() || (!uncertain && sale == null)) refresh()
    }

    private fun work(action: suspend () -> Unit) {
        if (state.value.busy) return
        state.update { it.copy(busy = true, message = null) }
        viewModelScope.launch {
            try {
                action()
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                state.update { it.copy(message = e.message ?: "No pudimos conectar. Intenta de nuevo.") }
            } finally {
                state.update { it.copy(busy = false) }
            }
        }
    }

    fun refresh() = work { loadAll() }

    private suspend fun loadAll() {
        val bootstrap = repo.bootstrap()
        val report = runCatching { repo.report() }.getOrNull()
        val customers = runCatching { repo.customers() }.getOrNull()
        state.update {
            it.copy(
                bootstrap = bootstrap,
                report = report ?: it.report,
                customers = customers ?: it.customers,
            )
        }
    }

    private suspend fun loadSummary() {
        val bootstrap = runCatching { repo.bootstrap() }.getOrNull()
        val report = runCatching { repo.report() }.getOrNull()
        val customers = runCatching { repo.customers() }.getOrNull()
        state.update {
            it.copy(
                bootstrap = bootstrap ?: it.bootstrap,
                report = report ?: it.report,
                customers = customers ?: it.customers,
            )
        }
    }

    fun connect(server: String) = work {
        check(state.value.sale == null && !state.value.uncertain) { "Resuelve el cobro actual antes de cambiar de servidor." }
        val normalized = normalizeServer(server, BuildConfig.DEBUG)
        val candidate = ApiRepository(normalized)
        val bootstrap = candidate.bootstrap()
        val report = candidate.report()
        val customers = runCatching { candidate.customers() }.getOrDefault(emptyList())
        check(prefs.edit().putString("server", normalized).commit()) { "No se pudo guardar la conexión" }
        repo = candidate
        state.value = ShopState(
            simulated = false, server = normalized, bootstrap = bootstrap,
            report = report, customers = customers,
        )
    }

    fun useSimulation() = work {
        check(state.value.sale == null && !state.value.uncertain) { "Conservamos el cobro pendiente; revísalo antes de cambiar." }
        check(prefs.edit().clear().commit())
        val demo = DemoRepository()
        repo = demo
        state.value = ShopState(
            bootstrap = demo.bootstrap(),
            report = demo.report(),
            customers = demo.customers(),
        )
    }

    fun select(employee: Employee) {
        if (state.value.busy) return
        state.update { it.copy(employee = employee, tab = "Inicio", message = null, customerDetail = null) }
    }

    fun leaveMockProfile() {
        val current = state.value
        if (!current.simulated || current.busy || current.sale != null || current.uncertain || current.cart.isNotEmpty()) return
        state.update {
            it.copy(employee = null, tab = "Inicio", message = null, customer = null, customerDetail = null)
        }
    }

    fun tab(value: String) {
        if (state.value.busy) return
        state.update { it.copy(tab = value, message = null) }
        refresh()
    }

    fun message(value: String) {
        state.update { it.copy(message = value) }
    }

    fun setPaymentMethod(method: String) {
        if (state.value.busy || state.value.sale != null) return
        state.update {
            it.copy(
                paymentMethod = method,
                customer = if (method == PAYMENT_FIADO) it.customer else null,
            )
        }
    }

    fun quantity(productId: Int, deltaMilli: Int) {
        if (state.value.busy || state.value.sale != null || state.value.uncertain) return
        runCatching { changeQuantity(state.value.cart, productId, deltaMilli) }
            .onSuccess { cart -> state.update { it.copy(cart = cart) } }
            .onFailure { message(it.message.orEmpty()) }
    }

    fun parse(text: String) = work {
        check(state.value.sale == null && !state.value.uncertain) { "Termina el cobro actual" }
        check(text.isNotBlank()) { "Escribe o dicta la venta" }
        val result = repo.parse(text.trim())
        var cart = state.value.cart
        result.items.forEach { line ->
            check(state.value.bootstrap?.products?.any { it.id == line.productId } == true) {
                "Producto desconocido. Actualiza el catálogo."
            }
            check(line.qtyMilli > 0) { "El servidor no devolvió una cantidad válida" }
            cart = changeQuantity(cart, line.productId, line.qtyMilli)
        }
        val unmatched = result.unmatched.takeIf { it.isNotEmpty() }
            ?.joinToString(prefix = "No encontré: ", separator = ", ")
        state.update {
            it.copy(
                cart = cart,
                message = listOfNotNull(
                    if (result.items.isEmpty()) "No encontramos productos en ese texto." else "Carrito actualizado.",
                    unmatched,
                    "Motor: ${result.engine}",
                ).joinToString(" "),
            )
        }
    }

    fun lookup(code: String) = work {
        check(state.value.sale == null && !state.value.uncertain) { "Termina el cobro actual" }
        check(code.isNotBlank()) { "Escribe el código de barras" }
        try {
            val product = repo.lookup(code.trim())
            addToCart(product, 1000, "Agregado desde el código: ${product.name}.")
        } catch (e: ApiFailure) {
            if (e.code == 404) {
                state.update { it.copy(linkCode = code.trim(), message = "Código sin enlazar. Elige el producto para guardarlo.") }
            } else {
                throw e
            }
        }
    }

    fun link(productId: Int) = work {
        val code = state.value.linkCode ?: return@work
        val product = repo.link(code, productId)
        state.update { it.copy(linkCode = null) }
        addToCart(product, 1000, "Código $code enlazado a ${product.name}.")
    }

    fun cancelLink() {
        state.update { it.copy(linkCode = null) }
    }

    private fun addToCart(product: Product, qtyMilli: Int, message: String) {
        val current = state.value
        check(current.bootstrap?.products?.any { it.id == product.id } == true) {
            "Actualiza el catálogo antes de agregar este producto."
        }
        state.update { it.copy(cart = changeQuantity(current.cart, product.id, qtyMilli), message = message) }
    }

    fun payCash(receivedCents: Long) {
        check(receivedCents > 0) { "Escribe el efectivo recibido" }
        submit(PAYMENT_CASH, receivedCents, null)
    }

    fun payPey() = submit(PAYMENT_PEY, null, null)

    fun payFiado() {
        val customer = state.value.customer
        if (customer == null) {
            message("Elige o agrega un cliente para el fiado")
            return
        }
        submit(PAYMENT_FIADO, null, customer.id)
    }

    private fun submit(method: String, cashReceivedCents: Long?, customerId: Int?) {
        work {
            val snapshot = state.value
            check(snapshot.sale == null && !snapshot.uncertain && snapshot.cart.isNotEmpty()) {
                "El carrito está vacío"
            }
            val employee = checkNotNull(snapshot.employee) { "Elige quién cobra" }
            val estimate = runCatching { cartEstimate(snapshot.cart, snapshot.bootstrap?.products.orEmpty()) }.getOrDefault(0)
            if (!snapshot.simulated) {
                check(prefs.edit().putBoolean("creating", true).commit()) {
                    "No se pudo proteger el intento. No se envió el cobro."
                }
            }
            state.update { it.copy(uncertain = true, message = null) }
            try {
                val created = repo.create(employee.id, snapshot.cart, method, cashReceivedCents, customerId)
                val sale = if (created.totalCents > 0) created else created.copy(
                    totalCents = estimate,
                    chargedCents = if (created.chargedCents > 0) created.chargedCents else estimate,
                )
                if (!snapshot.simulated && !persistSale(sale)) {
                    state.update { it.copy(sale = sale, uncertain = false, qrHidden = false) }
                    error("El cobro puede existir, pero no se pudo guardar. Revisa el servidor.")
                }
                state.update { it.copy(sale = sale, uncertain = false, qrHidden = false, linkCode = null) }
                if (sale.paymentMethod == PAYMENT_FIADO && sale.customerBalanceCents == null && sale.customerId != null) {
                    val detail = runCatching { repo.customer(sale.customerId) }.getOrNull()
                    if (detail != null) {
                        val updated = sale.copy(
                            customerName = detail.customer.name,
                            customerBalanceCents = detail.customer.balanceCents,
                        )
                        state.update { it.copy(sale = updated) }
                        if (!snapshot.simulated) persistSale(updated)
                    }
                }
                loadSummary()
            } catch (e: Exception) {
                if (e is ApiFailure && definitelyRejected(e.code)) {
                    if (snapshot.simulated || prefs.edit().putBoolean("creating", false).commit()) {
                        state.update { it.copy(uncertain = false) }
                    }
                }
                throw e
            }
        }
    }

    suspend fun poll() {
        val current = state.value.sale ?: return
        if (checking || state.value.busy) return
        if (current.paymentMethod != PAYMENT_PEY) return
        if (current.status !in setOf("pending", "por_conciliar", "expired")) return
        if (!state.value.simulated && state.value.server.isBlank()) return
        checking = true
        try {
            val remote = repo.status(current.id)
            val merged = remote.copy(
                qrImage = remote.qrImage.ifBlank { current.qrImage },
                qrId = remote.qrId ?: current.qrId,
                expiresAt = if (remote.expiresAt > 0.0) remote.expiresAt else current.expiresAt,
                totalCents = if (remote.totalCents > 0) remote.totalCents else current.totalCents,
                chargedCents = if (remote.chargedCents > 0) remote.chargedCents else current.chargedCents,
            )
            if (state.value.sale?.id != merged.id || state.value.sale?.settled == true) return
            if (!state.value.simulated) persistSale(merged)
            val becameSettled = merged.settled
            state.update { it.copy(sale = merged, message = null) }
            if (becameSettled) loadSummary()
        } catch (e: CancellationException) {
            throw e
        } catch (_: Exception) {
            state.update {
                it.copy(message = "Sin confirmación del servidor. No vuelvas a cobrar; retomaremos la consulta al conectar.")
            }
        } finally {
            checking = false
        }
    }

    fun checkNow() {
        viewModelScope.launch { poll() }
    }

    fun simulatePayment() = work {
        val sale = state.value.sale ?: return@work
        val demo = repo as? DemoRepository ?: error("La confirmación simulada solo existe en modo simulación")
        demo.simulatePaid(sale)
        val updated = demo.status(sale.id)
        val merged = updated.copy(
            qrImage = updated.qrImage.ifBlank { sale.qrImage },
            expiresAt = if (updated.expiresAt > 0.0) updated.expiresAt else sale.expiresAt,
            totalCents = if (updated.totalCents > 0) updated.totalCents else sale.totalCents,
            chargedCents = if (updated.chargedCents > 0) updated.chargedCents else sale.chargedCents,
        )
        state.update { it.copy(sale = merged, message = "Confirmación SIMULADA. No hubo pago.") }
        loadSummary()
    }

    fun hideQr() = work {
        checkNotNull(state.value.sale)
        if (!state.value.simulated) check(prefs.edit().putBoolean("qrHidden", true).commit())
        state.update {
            it.copy(
                qrHidden = true,
                message = "QR oculto en este teléfono. No se canceló el cobro; conservamos la venta para consultar pagos tardíos.",
            )
        }
    }

    fun newSale() {
        val current = state.value
        if (current.busy || current.sale?.settled != true) return
        if (!current.simulated && !prefs.edit().remove("sale").putBoolean("qrHidden", false).commit()) {
            message("No se pudo guardar. Conservamos la venta.")
            return
        }
        state.update {
            it.copy(
                sale = null, cart = emptyList(), customer = null, tab = "Cobrar",
                qrHidden = false, message = "Listo para el siguiente cobro.",
            )
        }
        refresh()
    }

    fun dismissSale() {
        val current = state.value
        if (current.busy) return
        val sale = current.sale ?: return
        if (!sale.settled && sale.status != "failed" && sale.status != "canceled" && sale.status != "expired") return
        if (!current.simulated) prefs.edit().remove("sale").putBoolean("qrHidden", false).commit()
        state.update { it.copy(sale = null, tab = "Cobrar", qrHidden = false) }
        refresh()
    }

    fun selectCustomer(customer: Customer) {
        if (state.value.busy) return
        state.update { it.copy(customer = customer) }
    }

    fun addCustomer(name: String, phone: String) = work {
        check(name.isNotBlank()) { "Escribe el nombre del cliente" }
        val customer = repo.addCustomer(name.trim(), phone.trim().ifBlank { null })
        state.update {
            it.copy(
                customers = (it.customers.filterNot { c -> c.id == customer.id } + customer)
                    .sortedBy { c -> c.name.lowercase() },
                customer = if (it.paymentMethod == PAYMENT_FIADO) customer else it.customer,
                message = "Cliente ${customer.name} agregado.",
            )
        }
    }

    fun openCustomer(id: Int) = work {
        val detail = repo.customer(id)
        state.update { it.copy(customerDetail = detail) }
    }

    fun closeCustomer() {
        state.update { it.copy(customerDetail = null) }
    }

    fun abono(amountCents: Long, note: String) = work {
        val detail = state.value.customerDetail ?: error("Elige un cliente")
        check(amountCents > 0) { "Escribe un monto mayor a cero" }
        val employee = checkNotNull(state.value.employee) { "Elige quién registra el abono" }
        repo.abono(detail.customer.id, amountCents, employee.id, note.trim().ifBlank { null })
        val refreshed = repo.customer(detail.customer.id)
        state.update {
            it.copy(
                customerDetail = refreshed,
                customers = it.customers.map { c -> if (c.id == refreshed.customer.id) refreshed.customer else c },
                customer = if (it.customer?.id == refreshed.customer.id) refreshed.customer else it.customer,
                message = "Abono registrado. Saldo: ${money(refreshed.customer.balanceCents)}.",
            )
        }
        loadSummary()
    }

    fun adjust(productId: Int, deltaMilli: Int) = work {
        val employee = checkNotNull(state.value.employee) { "Elige quién cobra" }
        val updated = repo.adjust(employee.id, productId, deltaMilli, "conteo")
        state.update { s ->
            s.copy(
                bootstrap = s.bootstrap?.copy(
                    products = s.bootstrap.products.map { if (it.id == updated.id) updated else it },
                ),
                message = "Ajuste guardado: ${updated.name} ahora tiene ${qtyText(updated.stockMilli, updated.unit)}.",
            )
        }
    }

    private fun persistSale(sale: Sale): Boolean {
        val safe = if (sale.qrImage.length > 2_000_000) sale.copy(qrImage = "") else sale
        return prefs.edit()
            .putString("sale", saleJson(safe).toString())
            .putBoolean("creating", false)
            .commit()
    }
}
