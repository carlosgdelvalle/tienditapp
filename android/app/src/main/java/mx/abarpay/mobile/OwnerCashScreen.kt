package mx.abarpay.mobile

import android.content.Context
import android.net.ConnectivityManager
import android.net.Network
import android.os.Handler
import android.os.Looper
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.relocation.BringIntoViewRequester
import androidx.compose.foundation.relocation.bringIntoViewRequester
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject
import java.util.UUID
import java.util.concurrent.TimeUnit

private data class CashProduct(
    val id: String,
    val name: String,
    val unit: String,
    val price: Long,
    val stockMilli: Int,
    val unlimited: Boolean,
) {
    fun canAdd(quantity: Int) = quantity < 1000 && (unlimited || stockMilli / 1000 > quantity)
}

private class OwnerCashApi(
    private val auth: OwnerAuth,
    baseUrl: String,
    tenantId: String,
) {
    private val path = baseUrl.trimEnd('/') + "/api/owner/pos/" + tenantId
    private val client = OkHttpClient.Builder().callTimeout(10, TimeUnit.SECONDS)
        .followRedirects(false).followSslRedirects(false).build()

    suspend fun lease(): JSONObject = request("/offline-lease", issueLease = true)

    suspend fun record(intent: JSONObject, offline: Boolean = false): JSONObject =
        request(if (offline) "/offline-sales" else "/sales", intent)

    private suspend fun request(suffix: String, intent: JSONObject? = null, issueLease: Boolean = false): JSONObject {
        val token = auth.accessToken() ?: throw ApiFailure(401, "Vuelve a entrar con tu celular.")
        return withContext(Dispatchers.IO) {
            val request = Request.Builder().url(path + suffix).header("Authorization", "Bearer " + token)
            if (intent != null) {
                request.header("Idempotency-Key", intent.getString("key")).post(
                    intent.getJSONObject("body").toString().toRequestBody("application/json".toMediaType()),
                )
            } else if (issueLease) {
                request.post("{}".toRequestBody("application/json".toMediaType()))
            }
            client.newCall(request.build()).execute().use { response ->
                val data = JSONObject(checkNotNull(response.body).string())
                if (!response.isSuccessful) {
                    throw ApiFailure(response.code, data.optString("detail", "No se pudo registrar la venta."))
                }
                data
            }
        }
    }
}

@Composable
internal fun cashNetworkAvailable(): Boolean {
    val context = LocalContext.current
    val manager = remember(context) { context.getSystemService(ConnectivityManager::class.java) }
    var available by remember(manager) { mutableStateOf(manager.activeNetwork != null) }
    DisposableEffect(manager) {
        val handler = Handler(Looper.getMainLooper())
        val callback = object : ConnectivityManager.NetworkCallback() {
            override fun onAvailable(network: Network) { handler.post { available = true } }
            override fun onLost(network: Network) {
                handler.post { available = manager.activeNetwork?.let { it != network } == true }
            }
        }
        manager.registerDefaultNetworkCallback(callback)
        onDispose { manager.unregisterNetworkCallback(callback) }
    }
    return available
}

@OptIn(ExperimentalFoundationApi::class, ExperimentalLayoutApi::class)
@Composable
internal fun OwnerCashScreen(auth: OwnerAuth, baseUrl: String, store: OwnerStore, onClose: () -> Unit) {
    val context = LocalContext.current
    val connectivity = remember(context) { context.getSystemService(ConnectivityManager::class.java) }
    val scope = rememberCoroutineScope()
    val api = remember(auth, baseUrl, store.tenantId) { OwnerCashApi(auth, baseUrl, store.tenantId) }
    val prefs = remember(context) { context.getSharedPreferences("abarpay_owner_cash", Context.MODE_PRIVATE) }
    val journal = "cash:" + baseUrl + ":" + store.tenantId
    var pending by remember(journal) {
        mutableStateOf(prefs.getString(journal + ":intent", null)?.let(::JSONObject))
    }
    var receipt by remember(journal) {
        mutableStateOf(prefs.getString(journal + ":receipt", null)?.let(::JSONObject))
    }
    val offlineJournal = remember(journal) { OfflineCashJournal(context, baseUrl, store.tenantId) }
    var offlineState by remember(journal) { mutableStateOf<OfflineCashState?>(null) }
    val networkAvailable = cashNetworkAvailable()
    var offlineSelected by rememberSaveable { mutableStateOf(false) }
    val offlineMode = !networkAvailable || offlineSelected
    val local = offlineState
    val products = local?.lease?.getJSONArray("items")?.objects().orEmpty().map {
        CashProduct(
            it.getString("id"), it.getString("name"), it.getString("unit"),
            it.getLong("priceCents"), it.getInt("stockMilli"), it.getBoolean("unlimitedStock"),
        )
    }
    var draft by remember(journal) { mutableStateOf(CashDraft()) }
    var restored by remember(journal) { mutableStateOf(false) }
    val cart = draft.quantities
    val cash = draft.cash
    var working by remember { mutableStateOf("") }
    var error by remember { mutableStateOf("") }
    val total = products.sumOf { it.price * (cart[it.id] ?: 0) }
    val availableIds = products.mapTo(mutableSetOf()) { it.id }
    val missingProducts = cart.keys.any { it !in availableIds }
    val overStock = products.any { !it.unlimited && (cart[it.id] ?: 0) > it.stockMilli.coerceAtLeast(0) / 1000 }
    val paymentAnchor = remember { BringIntoViewRequester() }

    fun editDraft(updated: CashDraft) {
        try {
            offlineJournal.saveDraft(updated)
            draft = updated
            if (updated.quantities.isEmpty()) restored = false
        } catch (_: Exception) {
            error = "No se pudo guardar el cambio. Intenta de nuevo antes de cobrar."
        }
    }

    fun clearDraft() {
        offlineJournal.clearDraft()
        draft = CashDraft()
        restored = false
    }

    fun runAction(message: String, action: suspend () -> Unit) {
        if (working.isNotEmpty()) return
        working = message
        error = ""
        scope.launch {
            try {
                action()
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (failure: ApiFailure) {
                error = if (failure.code >= 500 && pending != null) {
                    "Venta por confirmar. Consulta el resultado antes de volver a cobrar."
                } else {
                    failure.message.orEmpty()
                }
            } catch (_: Exception) {
                error = if (pending != null) "Venta por confirmar. No vuelvas a cobrar."
                else "Revisa tu conexión y vuelve a intentar."
            } finally {
                working = ""
            }
        }
    }

    suspend fun persist(state: OfflineCashState, clearDraft: Boolean = false) {
        offlineJournal.save(state, clearDraft)
        offlineState = state
    }

    suspend fun refreshLease() {
        val state = checkNotNull(offlineState)
        try {
            persist(state.copy(lease = offlineJournal.anchor(api.lease())))
        } catch (failure: ApiFailure) {
            if (failure.code == 401 || failure.code == 403) persist(state.copy(lease = null))
            throw failure
        }
    }

    fun loadCatalog() = runAction("Cargando el catálogo…") { refreshLease() }

    fun syncCash() = runAction("Sincronizando ventas…") {
        offlineSelected = false
        var state = checkNotNull(offlineState)
        while (state.pending.isNotEmpty()) {
            val attempt = state.pending.first()
            val result = api.record(attempt, offline = true)
            val expectedId = cashSaleId(store.tenantId, attempt.getString("key"))
            check(result.getString("saleId") == expectedId)
            state = state.copy(
                pending = state.pending.drop(1),
                receipt = if (state.receipt?.optString("saleId") == expectedId) result else state.receipt,
            )
            persist(state)
        }
        if (cart.isEmpty()) refreshLease()
    }

    fun record(received: Long?) = runAction("Confirmando la venta…") {
        val attempt = pending ?: JSONObject()
            .put("key", UUID.randomUUID().toString())
            .put("body", JSONObject().put("items", JSONArray(cart.map { (id, count) ->
                JSONObject().put("productId", id).put("qtyMilli", count * 1000)
            })).put("expectedTotalCents", total).put("cashReceivedCents", received))
        if (pending == null) {
            check(prefs.edit().putString(journal + ":intent", attempt.toString()).commit())
            pending = attempt
        }
        val sale = try {
            api.record(attempt)
        } catch (failure: ApiFailure) {
            // Price and stock checks are performed before the first commit.
            // Ambiguous responses keep the journal so a retry uses the same folio.
            if (failure.code == 409 && failure.message in setOf(
                    "El precio cambió. Actualiza el catálogo antes de cobrar.", "Inventario insuficiente",
                )
            ) {
                check(prefs.edit().remove(journal + ":intent").commit())
                pending = null
                refreshLease()
            }
            throw failure
        }
        check(prefs.edit().remove(journal + ":intent").putString(journal + ":receipt", sale.toString()).commit())
        pending = null
        receipt = sale
        clearDraft()
    }

    fun recordOffline(received: Long) = runAction("Guardando la venta en este celular…") {
        val state = checkNotNull(offlineState)
        val occurred = offlineJournal.occurredAt(state.lease)
        if (occurred == null) {
            error = "Conéctate para renovar el acceso a caja antes de recibir efectivo."
            return@runAction
        }
        val lease = JSONObject(checkNotNull(state.lease).toString())
        val key = UUID.randomUUID().toString()
        val saleId = cashSaleId(store.tenantId, key)
        val items = JSONArray(cart.map { (id, count) ->
            JSONObject().put("productId", id).put("qtyMilli", count * 1000)
        })
        val body = JSONObject().put("items", items).put("expectedTotalCents", total)
            .put("cashReceivedCents", received).put("leaseId", lease.getString("leaseId")).put("occurredAt", occurred)
        for (product in lease.getJSONArray("items").objects()) {
            val count = cart[product.getString("id")] ?: continue
            if (!product.getBoolean("unlimitedStock")) {
                product.put("stockMilli", product.getInt("stockMilli") - count * 1000)
            }
        }
        val localReceipt = JSONObject().put("saleId", saleId).put("totalCents", total)
            .put("changeCents", received - total).put("offlinePending", true)
        val attempt = JSONObject().put("key", key).put("body", body)
        persist(OfflineCashState(lease, state.pending + attempt, localReceipt), clearDraft = true)
        draft = CashDraft()
        restored = false
    }

    LaunchedEffect(journal) {
        try {
            val state = offlineJournal.read()
            val saved = offlineJournal.readDraft()
            draft = saved
            restored = saved.quantities.isNotEmpty()
            offlineState = state
        } catch (cancelled: CancellationException) {
            throw cancelled
        } catch (_: Exception) {
            error = "No se pudo abrir la caja guardada. Contacta a Abarpay antes de cobrar."
        }
    }
    LaunchedEffect(journal, local != null, networkAvailable) {
        if (local != null && networkAvailable && !offlineSelected && pending == null) {
            if (local.pending.isNotEmpty()) syncCash()
            else if (receipt == null && cart.isEmpty()) loadCatalog()
        }
    }
    BackHandler { if (working.isEmpty()) onClose() }
    val savedSale = receipt ?: local?.receipt
    val authorized = offlineJournal.occurredAt(local?.lease) != null
    Column(Modifier.fillMaxSize().safeDrawingPadding().imePadding()) {
        Column(
            Modifier.weight(1f).fillMaxWidth().verticalScroll(rememberScrollState()).padding(24.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text("Caja en efectivo", style = MaterialTheme.typography.headlineSmall)
            Text(store.name, style = MaterialTheme.typography.titleMedium)
            if (offlineMode) Text("Sin conexión a la caja · Solo efectivo.")
            if (!local?.pending.isNullOrEmpty()) {
                Text("Ventas por sincronizar: ${local?.pending?.size}")
                if (networkAvailable) {
                    OutlinedButton(onClick = ::syncCash, enabled = working.isEmpty()) { Text("Sincronizar ventas") }
                }
            }
            if (savedSale != null) {
                Text(
                    if (savedSale.optBoolean("offlinePending")) "Venta guardada en este celular" else "Venta registrada",
                    style = MaterialTheme.typography.titleLarge,
                )
                if (savedSale.optBoolean("offlinePending")) Text("Se verá en la consola al sincronizar.")
                Text("Total " + money(savedSale.getLong("totalCents")), modifier = Modifier.testTag("owner-cash-receipt-total"))
                Text("Cambio " + money(savedSale.getLong("changeCents")))
                Text("Folio")
                SelectionContainer {
                    Text(savedSale.getString("saleId"), modifier = Modifier.testTag("owner-cash-receipt-id"))
                }
                Button(
                    onClick = {
                        runAction("Abriendo otra venta…") {
                            clearDraft()
                            if (receipt != null) {
                                check(prefs.edit().remove(journal + ":receipt").commit())
                                receipt = null
                            } else {
                                persist(checkNotNull(offlineState).copy(receipt = null))
                            }
                            if (!offlineMode && offlineState?.pending.isNullOrEmpty()) refreshLease()
                        }
                    },
                    enabled = working.isEmpty(),
                ) { Text("Nueva venta") }
            } else if (pending != null) {
                Text("Venta por confirmar", style = MaterialTheme.typography.titleLarge)
                Text("Total " + money(pending!!.getJSONObject("body").getLong("expectedTotalCents")))
                Text("Consulta el resultado del mismo cobro antes de recibir efectivo otra vez.")
                Button(onClick = { record(null) }, enabled = working.isEmpty() && networkAvailable) { Text("Consultar venta pendiente") }
            } else if (local == null) {
                if (error.isBlank()) Text("Abriendo la caja guardada…")
            } else if (products.isEmpty()) {
                if (working.isEmpty()) Text(
                    if (offlineMode) "Conéctate para preparar esta caja antes de cobrar."
                    else "Agrega productos en la consola para empezar a cobrar."
                )
                OutlinedButton(onClick = ::loadCatalog, enabled = working.isEmpty() && networkAvailable) { Text("Actualizar catálogo") }
            } else {
                if (restored) Text("Retomaste una venta sin registrar.")
                if (missingProducts) {
                    Text("Hay productos del carrito que ya no aparecen en el catálogo.")
                    OutlinedButton(
                        onClick = { editDraft(draft.copy(quantities = cart.filterKeys { it in availableIds })) },
                        enabled = working.isEmpty(),
                    ) { Text("Quitar productos que ya no están") }
                }
                if (overStock) Text("Quita del carrito las piezas que ya no están disponibles.")
                if (offlineMode && !authorized) Text("Conéctate para renovar el acceso a caja antes de recibir efectivo.")
                if (cart.isEmpty()) OutlinedButton(onClick = ::loadCatalog, enabled = working.isEmpty() && networkAvailable) {
                    Text(if (networkAvailable) "Actualizar catálogo" else "Catálogo guardado")
                }
                if (networkAvailable && authorized) OutlinedButton(
                    onClick = {
                        if (offlineSelected && !local.pending.isEmpty()) syncCash()
                        else offlineSelected = !offlineSelected
                    },
                    enabled = working.isEmpty(),
                ) { Text(if (offlineSelected) "Volver a caja en línea" else "Trabajar sin conexión") }
                products.forEach { product ->
                    val count = cart[product.id] ?: 0
                    Text(product.name + " · " + money(product.price) + " / " + product.unit)
                    Text(if (product.unlimited) "Existencia ilimitada" else
                        "Existencia: " + qtyText(product.stockMilli, product.unit))
                    FlowRow(
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                        verticalArrangement = Arrangement.spacedBy(4.dp),
                    ) {
                        Button(
                            onClick = { editDraft(draft.copy(quantities = cart + (product.id to (count + 1)))) },
                            enabled = product.canAdd(count) && working.isEmpty() && (!offlineMode || authorized),
                        ) { Text("Agregar ${product.name}") }
                        if (count > 0) OutlinedButton(
                            onClick = {
                                val quantities = if (count == 1) cart - product.id else cart + (product.id to (count - 1))
                                editDraft(CashDraft(quantities, cash.takeIf { quantities.isNotEmpty() }.orEmpty()))
                            },
                            enabled = working.isEmpty(),
                        ) { Text("Quitar ($count)") }
                    }
                    HorizontalDivider()
                }
                val received = parseCashCents(cash)
                Column(Modifier.bringIntoViewRequester(paymentAnchor), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    OutlinedTextField(
                        value = cash,
                        onValueChange = { editDraft(draft.copy(cash = it)) },
                        label = { Text("Efectivo recibido (MXN)") },
                        enabled = working.isEmpty(),
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth(),
                    )
                    if (received != null && received >= total) Text("Cambio " + money(received - total))
                    Button(
                        onClick = {
                            if (offlineMode || connectivity.activeNetwork == null) recordOffline(checkNotNull(received))
                            else record(received)
                        },
                        enabled = working.isEmpty() && cart.isNotEmpty() && received != null &&
                            !missingProducts && !overStock && (if (offlineMode) authorized else local.pending.isEmpty()) &&
                            received >= total && received <= Int.MAX_VALUE.toLong(),
                        modifier = Modifier.fillMaxWidth(),
                    ) { Text("Registrar venta en efectivo") }
                }
            }
            if (working.isNotEmpty()) {
                Text(working)
                LinearProgressIndicator(Modifier.fillMaxWidth())
            }
            if (error.isNotBlank()) Text(error, color = MaterialTheme.colorScheme.error)
            OutlinedButton(onClick = onClose, enabled = working.isEmpty()) { Text("Volver") }
        }
        if (local != null && savedSale == null && pending == null && products.isNotEmpty()) {
            Surface(tonalElevation = 4.dp, modifier = Modifier.fillMaxWidth()) {
                Row(
                    Modifier.padding(horizontal = 24.dp, vertical = 8.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    Text(
                        "Total " + money(total),
                        style = MaterialTheme.typography.titleLarge,
                        modifier = Modifier.weight(1f).testTag("cash-running-total")
                            .semantics { liveRegion = LiveRegionMode.Polite },
                    )
                    TextButton(
                        onClick = { scope.launch { paymentAnchor.bringIntoView() } },
                        enabled = cart.isNotEmpty() && working.isEmpty(),
                    ) { Text("Ir al cobro") }
                }
            }
        }
    }
}
