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
    val simulated: Boolean = true, val server: String = "", val bootstrap: Bootstrap? = null,
    val employee: Employee? = null, val report: Report? = null, val cart: List<CartLine> = emptyList(),
    val sale: Sale? = null, val uncertain: Boolean = false, val busy: Boolean = false,
    val message: String? = null, val tab: String = "Inicio", val qrHidden: Boolean = false
)
class ShopViewModel(app: Application): AndroidViewModel(app) {
    private val prefs = app.getSharedPreferences("development_session", 0)
    private var repo: ShopRepository = DemoRepository()
    private val state = MutableStateFlow(ShopState())
    val ui = state.asStateFlow()
    private var checking = false
    init {
        val server = prefs.getString("server", "").orEmpty()
        val (sale, uncertain) = recoverJournal(prefs.getString("sale", null), prefs.getBoolean("creating", false))
        if (server.isNotBlank()) {
            repo = ApiRepository(server)
            state.value = ShopState(simulated = false, server = server, sale = sale, uncertain = uncertain,
                qrHidden = prefs.getBoolean("qrHidden", false))
        } else if (sale != null || uncertain) {
            state.value = ShopState(simulated = false, sale = sale, uncertain = true,
                message = "No se pudo recuperar la conexión del cobro. No generes otro intento.")
        }
        if (server.isNotBlank() || (!uncertain && sale == null)) refresh()
    }
    private fun work(action: suspend () -> Unit) {
        if (state.value.busy) return
        state.update { it.copy(busy = true, message = null) }
        viewModelScope.launch {
            try { action() }
            catch (e: CancellationException) { throw e }
            catch (e: Exception) { state.update { it.copy(message = e.message ?: "No pudimos conectar. Intenta de nuevo.") } }
            finally { state.update { it.copy(busy = false) } }
        }
    }
    fun refresh() = work {
        val b = repo.bootstrap()
        state.update { it.copy(bootstrap = b) }
        val report = repo.report()
        state.update { it.copy(report = report) }
    }
    fun connect(server: String) = work {
        check(state.value.sale == null && !state.value.uncertain) { "Resuelve el cobro actual antes de cambiar de servidor." }
        val normalized = normalizeServer(server, BuildConfig.DEBUG)
        val candidate = ApiRepository(normalized)
        val b = candidate.bootstrap()
        val report = candidate.report()
        check(prefs.edit().putString("server", normalized).commit()) { "No se pudo guardar la conexión" }
        repo = candidate
        state.value = ShopState(simulated = false, server = normalized, bootstrap = b, report = report)
    }
    fun useSimulation() = work {
        check(state.value.sale == null && !state.value.uncertain) { "Conservamos el cobro pendiente; revísalo antes de cambiar." }
        check(prefs.edit().clear().commit())
        repo = DemoRepository()
        state.value = ShopState(bootstrap = repo.bootstrap(), report = repo.report())
    }
    fun select(employee: Employee) { if (!state.value.busy) state.update { it.copy(employee = employee) } }
    fun leaveMockProfile() {
        val current = state.value
        if (!current.simulated || current.busy || current.sale != null || current.uncertain || current.cart.isNotEmpty()) return
        state.update { it.copy(employee = null, tab = "Inicio", message = null) }
    }
    fun tab(value: String) {
        if (state.value.busy) return
        state.update { it.copy(tab = value, message = null) }
        if (value != "Cobrar") refresh()
    }
    fun message(value: String) { state.update { it.copy(message = value) } }
    fun quantity(id: Int, delta: Int) {
        if (state.value.busy || state.value.sale != null || state.value.uncertain) return
        runCatching { changeQuantity(state.value.cart, id, delta) }
            .onSuccess { cart -> state.update { it.copy(cart = cart) } }.onFailure { message(it.message.orEmpty()) }
    }
    fun parse(text: String) = work {
        check(state.value.sale == null && !state.value.uncertain)
        val result = repo.parse(text)
        var cart = state.value.cart
        result.items.forEach { line ->
            check(state.value.bootstrap?.products?.any { it.id == line.productId } == true) { "Producto desconocido. Actualiza el catálogo." }
            check(line.qty > 0)
            cart = changeQuantity(cart, line.productId, line.qty)
        }
        state.update { it.copy(cart = cart, message = listOfNotNull(result.warning,
            result.unmatched.takeIf { x -> x.isNotEmpty() }?.joinToString(prefix = "No encontré: ")).joinToString("\n").ifBlank { "Carrito actualizado. Revisa antes de cobrar." }) }
    }
    fun lookup(code: String) = work {
        check(state.value.sale == null && !state.value.uncertain)
        val id = repo.lookup(code)
        check(state.value.bootstrap?.products?.any { it.id == id } == true) { "Actualiza el catálogo antes de agregar este código." }
        val cart = changeQuantity(state.value.cart, id, 1)
        state.update { it.copy(cart = cart, message = "Producto agregado. Revisa el carrito.") }
    }
    fun createSale() = work {
        val snapshot = state.value
        check(snapshot.sale == null && !snapshot.uncertain && snapshot.cart.isNotEmpty())
        val employee = checkNotNull(snapshot.employee)
        // Durable marker BEFORE the network call. A killed process cannot silently retry a POST.
        if (!snapshot.simulated) check(prefs.edit().putBoolean("creating", true).commit()) { "No se pudo proteger el intento. No se envió el cobro." }
        state.update { it.copy(uncertain = true) }
        try {
            val sale = repo.create(employee.id, snapshot.cart)
            if (!snapshot.simulated) check(prefs.edit().putString("sale", saleJson(sale).toString())
                .putBoolean("creating", false).putBoolean("qrHidden", false).commit()) { "El cobro puede existir, pero no se pudo guardar. Revisa el servidor." }
            state.update { it.copy(sale = sale, uncertain = false, qrHidden = false) }
        } catch (e: Exception) {
            if (e is ApiFailure && definitelyRejected(e.code)) {
                if (snapshot.simulated || prefs.edit().putBoolean("creating", false).commit()) state.update { it.copy(uncertain = false) }
            }
            throw e
        }
    }
    suspend fun poll() {
        val sale = state.value.sale ?: return
        if (checking || state.value.busy || sale.paid || (!state.value.simulated && state.value.server.isBlank())) return
        checking = true
        try {
            val updated = repo.status(sale)
            if (state.value.sale?.id != updated.id || state.value.sale?.paid == true) return
            if (!state.value.simulated) check(prefs.edit().putString("sale", saleJson(updated).toString()).commit())
            state.update { it.copy(sale = updated, message = null) }
        } catch (e: CancellationException) { throw e }
        catch (_: Exception) { state.update { it.copy(message = "Sin confirmación del servidor. No vuelvas a cobrar; retomaremos la consulta al conectar.") } }
        finally { checking = false }
    }
    fun checkNow() { viewModelScope.launch { poll() } }
    fun simulatePayment() {
        val sale = state.value.sale ?: return
        (repo as? DemoRepository)?.simulatePaid(sale)
        checkNow()
    }
    fun hideQr() = work {
        checkNotNull(state.value.sale)
        if (!state.value.simulated) check(prefs.edit().putBoolean("qrHidden", true).commit())
        state.update { it.copy(qrHidden = true, message = "QR oculto en este teléfono. No se canceló el cobro; conservamos la venta para consultar pagos tardíos.") }
    }
    fun newSale() {
        if (state.value.busy || state.value.sale?.paid != true) return
        if (!state.value.simulated && !prefs.edit().remove("sale").putBoolean("qrHidden", false).commit()) {
            message("No se pudo guardar. Conservamos la venta."); return
        }
        state.update { it.copy(sale = null, cart = emptyList(), tab = "Cobrar", qrHidden = false) }
        refresh()
    }
}
