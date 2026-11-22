package mx.abarpay.mobile

import android.content.Context
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
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

    suspend fun catalog(): List<CashProduct> = request("/catalog").getJSONArray("items").objects().map {
        CashProduct(
            it.getString("id"), it.getString("name"), it.getString("unit"),
            it.getLong("priceCents"), it.getInt("stockMilli"), it.getBoolean("unlimitedStock"),
        )
    }

    suspend fun record(intent: JSONObject): JSONObject = request("/sales", intent)

    private suspend fun request(suffix: String, intent: JSONObject? = null): JSONObject {
        val token = auth.accessToken() ?: throw ApiFailure(401, "Vuelve a entrar con tu celular.")
        return withContext(Dispatchers.IO) {
            val request = Request.Builder().url(path + suffix).header("Authorization", "Bearer " + token)
            if (intent != null) {
                request.header("Idempotency-Key", intent.getString("key")).post(
                    intent.getJSONObject("body").toString().toRequestBody("application/json".toMediaType()),
                )
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
internal fun OwnerCashScreen(auth: OwnerAuth, baseUrl: String, store: OwnerStore, onClose: () -> Unit) {
    val context = LocalContext.current
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
    var products by remember { mutableStateOf(emptyList<CashProduct>()) }
    val cart = remember { mutableStateMapOf<String, Int>() }
    var cash by rememberSaveable { mutableStateOf("") }
    var working by remember { mutableStateOf("") }
    var error by remember { mutableStateOf("") }
    val total = products.sumOf { it.price * (cart[it.id] ?: 0) }

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

    fun loadCatalog() = runAction("Cargando el catálogo…") { products = api.catalog() }

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
                cart.clear()
                products = api.catalog()
            }
            throw failure
        }
        check(prefs.edit().remove(journal + ":intent").putString(journal + ":receipt", sale.toString()).commit())
        pending = null
        receipt = sale
        cart.clear()
        cash = ""
    }

    LaunchedEffect(journal) {
        if (pending == null && receipt == null) loadCatalog()
    }
    BackHandler { if (working.isEmpty()) onClose() }
    Column(
        Modifier.fillMaxSize().safeDrawingPadding().imePadding().verticalScroll(rememberScrollState()).padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text("Caja en efectivo", style = MaterialTheme.typography.headlineSmall)
        Text(store.name, style = MaterialTheme.typography.titleMedium)
        val savedSale = receipt
        if (savedSale != null) {
            Text("Venta registrada", style = MaterialTheme.typography.titleLarge)
            Text("Total " + money(savedSale.getLong("totalCents")), modifier = Modifier.testTag("owner-cash-receipt-total"))
            Text("Cambio " + money(savedSale.getLong("changeCents")))
            Text("Folio")
            SelectionContainer {
                Text(savedSale.getString("saleId"), modifier = Modifier.testTag("owner-cash-receipt-id"))
            }
            Button(
                onClick = {
                    if (prefs.edit().remove(journal + ":receipt").commit()) {
                        receipt = null
                        loadCatalog()
                    } else {
                        error = "No se pudo abrir otra venta. Intenta de nuevo."
                    }
                },
            ) { Text("Nueva venta") }
        } else if (pending != null) {
            Text("Venta por confirmar", style = MaterialTheme.typography.titleLarge)
            Text("Total " + money(pending!!.getJSONObject("body").getLong("expectedTotalCents")))
            Text("Consulta el resultado del mismo cobro antes de recibir efectivo otra vez.")
            Button(onClick = { record(null) }, enabled = working.isEmpty()) { Text("Consultar venta pendiente") }
        } else if (products.isEmpty()) {
            if (working.isEmpty()) Text("Agrega productos en la consola para empezar a cobrar.")
            OutlinedButton(onClick = ::loadCatalog, enabled = working.isEmpty()) { Text("Actualizar catálogo") }
        } else {
            if (cart.isEmpty()) OutlinedButton(onClick = ::loadCatalog, enabled = working.isEmpty()) {
                Text("Actualizar catálogo")
            }
            products.forEach { product ->
                val count = cart[product.id] ?: 0
                Text(product.name + " · " + money(product.price) + " / " + product.unit)
                Text(if (product.unlimited) "Existencia ilimitada" else
                    "Existencia: " + qtyText(product.stockMilli, product.unit))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(
                        onClick = { cart[product.id] = count + 1 },
                        enabled = product.canAdd(count) && working.isEmpty(),
                    ) { Text("Agregar ${product.name}") }
                    if (count > 0) OutlinedButton(
                        onClick = { if (count == 1) cart.remove(product.id) else cart[product.id] = count - 1 },
                        enabled = working.isEmpty(),
                    ) { Text("Quitar ($count)") }
                }
                HorizontalDivider()
            }
            val received = parseCashCents(cash)
            Text("Total " + money(total), style = MaterialTheme.typography.titleLarge)
            OutlinedTextField(
                value = cash,
                onValueChange = { cash = it },
                label = { Text("Efectivo recibido (MXN)") },
                enabled = working.isEmpty(),
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )
            if (received != null && received >= total) Text("Cambio " + money(received - total))
            Button(
                onClick = { record(received) },
                enabled = working.isEmpty() && cart.isNotEmpty() && received != null &&
                    received >= total && received <= Int.MAX_VALUE.toLong(),
                modifier = Modifier.fillMaxWidth(),
            ) { Text("Registrar venta en efectivo") }
        }
        if (working.isNotEmpty()) {
            Text(working)
            LinearProgressIndicator(Modifier.fillMaxWidth())
        }
        if (error.isNotBlank()) Text(error, color = MaterialTheme.colorScheme.error)
        OutlinedButton(onClick = onClose, enabled = working.isEmpty()) { Text("Volver") }
    }
}
