package mx.abarpay.mobile

import android.content.Context
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
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
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch
import org.json.JSONArray
import org.json.JSONObject
import java.util.UUID

@Composable
internal fun EmployeeWorkspace(auth: OwnerAuth, baseUrl: String) {
    val api = remember(auth, baseUrl) { EmployeeApi(baseUrl, auth) }
    val context = LocalContext.current
    val connected = cashNetworkAvailable()
    val prefs = remember(context) { context.getSharedPreferences("abarpay_employee_cash_stores", Context.MODE_PRIVATE) }
    var cashStores by remember(baseUrl) {
        mutableStateOf(JSONArray(prefs.getString(baseUrl, "[]")).objects().map {
            EmployeeAccess(it.getString("id"), it.getString("name"), true, false, false)
        })
    }
    val scope = rememberCoroutineScope()
    var stores by remember { mutableStateOf<List<EmployeeAccess>?>(null) }
    var selectedId by rememberSaveable { mutableStateOf("") }
    var operation by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf("") }
    val lifecycle = LocalLifecycleOwner.current.lifecycle

    fun refresh() {
        if (busy || !connected) return
        busy = true
        error = ""
        scope.launch {
            try {
                val current = api.memberships()
                stores = current
                cashStores = current.filter { it.canSell }.map {
                    it.copy(canFiado = false, canInventory = false)
                }
                prefs.edit().putString(baseUrl, JSONArray(cashStores.map {
                    JSONObject().put("id", it.tenantId).put("name", it.name)
                }).toString()).apply()
                if (current.none { it.tenantId == selectedId }) {
                    selectedId = current.singleOrNull()?.tenantId.orEmpty()
                }
                val access = current.find { it.tenantId == selectedId }
                val allowed = when (operation) {
                    "cash" -> access?.canSell
                    "inventory" -> access?.canInventory
                    "fiado" -> access?.canFiado
                    else -> true
                }
                if (allowed != true) operation = ""
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (failure: Exception) {
                stores = null
                operation = ""
                error = (failure as? ApiFailure)?.message ?: "Revisa tu conexión e intenta de nuevo."
            } finally {
                busy = false
            }
        }
    }

    LaunchedEffect(api, connected) { refresh() }
    DisposableEffect(lifecycle, api, connected) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME) refresh()
        }
        lifecycle.addObserver(observer)
        onDispose { lifecycle.removeObserver(observer) }
    }

    val availableStores = if (connected) stores.orEmpty() else cashStores
    val access = availableStores.find { it.tenantId == selectedId } ?: availableStores.singleOrNull()
    val closeOperation: () -> Unit = { operation = ""; refresh() }
    if (access != null) {
        if (operation == "cash" && access.canSell) {
            OwnerCashScreen(auth, baseUrl, OwnerStore(access.tenantId, access.name), closeOperation)
            return
        }
        if ((operation == "inventory" && access.canInventory) || (operation == "fiado" && access.canFiado)) {
            EmployeeLedgerScreen(api, baseUrl, access, operation, closeOperation)
            return
        }
    }

    EmployeeLayout {
        Text("Mi turno", style = MaterialTheme.typography.headlineSmall)
        if (availableStores.size > 1) {
            availableStores.forEach { store ->
                OutlinedButton(onClick = { selectedId = store.tenantId }, enabled = !busy) {
                    Text(if (selectedId == store.tenantId) "Tienda elegida: ${store.name}" else store.name)
                }
            }
        }
        if (access != null) {
            Text(access.name, style = MaterialTheme.typography.titleLarge)
            if (access.canSell) Button(onClick = { operation = "cash" }, enabled = !busy,
                modifier = Modifier.fillMaxWidth().testTag("employee-cash")) { Text("Cobrar en efectivo") }
            if (access.canInventory) Button(onClick = { operation = "inventory" }, enabled = !busy,
                modifier = Modifier.fillMaxWidth().testTag("employee-inventory")) { Text("Inventario") }
            if (access.canFiado) Button(onClick = { operation = "fiado" }, enabled = !busy,
                modifier = Modifier.fillMaxWidth().testTag("employee-fiado")) { Text("Fiado") }
            if (!access.canSell && !access.canInventory && !access.canFiado) {
                Text("Tu acceso está activo. Pide al dueño que te asigne una tarea.")
            }
        }
        if (!connected) {
            Text(if (cashStores.isEmpty()) "Conéctate para consultar tu acceso."
                else "Sin conexión · Solo caja en efectivo.")
        } else if (stores?.isEmpty() == true) {
            Text("Por ahora no tienes acceso a una tienda. Habla con el dueño.")
        }
        if (busy) {
            Text("Revisando tu acceso…")
            LinearProgressIndicator(Modifier.fillMaxWidth())
        }
        if (error.isNotBlank()) Text(error, color = MaterialTheme.colorScheme.error)
        OutlinedButton(onClick = ::refresh, enabled = !busy && connected) { Text("Actualizar acceso") }
    }
}

private fun countedMilli(text: String): Int? = text.trim().replace(',', '.')
    .takeIf { Regex("^\\d{1,7}(\\.\\d{1,3})?$").matches(it) }
    ?.toBigDecimal()?.movePointRight(3)?.toLong()
    ?.takeIf { it <= Int.MAX_VALUE }?.toInt()

@Composable
private fun EmployeeLedgerScreen(
    api: EmployeeApi,
    baseUrl: String,
    access: EmployeeAccess,
    mode: String,
    onClose: () -> Unit,
) {
    val inventory = mode == "inventory"
    val path = "/api/employee/" + access.tenantId + if (inventory) "/inventory" else "/fiado/customers"
    val context = LocalContext.current
    val prefs = remember(context) { context.getSharedPreferences("abarpay_employee_work", Context.MODE_PRIVATE) }
    val journal = baseUrl + ":" + access.tenantId + ":" + mode
    val scope = rememberCoroutineScope()
    var pending by remember(journal) { mutableStateOf(prefs.getString(journal, null)?.let(::JSONObject)) }
    var rows by remember { mutableStateOf(emptyList<JSONObject>()) }
    var selected by remember { mutableStateOf<JSONObject?>(null) }
    var detail by remember { mutableStateOf<JSONObject?>(null) }
    var amount by remember { mutableStateOf("") }
    var note by remember { mutableStateOf("") }
    var payment by remember { mutableStateOf(false) }
    var progress by remember { mutableStateOf("") }
    var notice by remember { mutableStateOf("") }
    var error by remember { mutableStateOf(false) }

    fun run(message: String, work: suspend () -> Unit) {
        if (progress.isNotEmpty()) return
        progress = message
        notice = ""
        error = false
        scope.launch {
            try {
                work()
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (failure: Exception) {
                if (failure is ApiFailure && failure.code in setOf(401, 403)) {
                    rows = emptyList()
                    selected = null
                    detail = null
                }
                notice = (failure as? ApiFailure)?.message ?: "No se pudo confirmar. Revisa tu conexión."
                error = true
            } finally {
                progress = ""
            }
        }
    }

    suspend fun refreshData() {
        rows = api.request(path).getJSONArray("items").objects()
        selected?.let { item ->
            val id = item.getString("id")
            selected = rows.find { it.getString("id") == id }
            detail = if (!inventory && selected != null) api.request("$path/$id") else null
        }
    }

    fun record(body: JSONObject?, endpoint: String?) = run("Guardando…") {
        val attempt = pending ?: JSONObject().put("url", checkNotNull(endpoint))
            .put("key", UUID.randomUUID().toString()).put("body", checkNotNull(body))
        if (pending == null) {
            check(prefs.edit().putString(journal, attempt.toString()).commit())
            pending = attempt
        }
        try {
            api.request(attempt.getString("url"), attempt.getJSONObject("body"), attempt.getString("key"))
        } catch (failure: ApiFailure) {
            if (failure.code in setOf(400, 404, 409, 422)) {
                check(prefs.edit().remove(journal).commit())
                pending = null
                if (inventory && failure.code == 409) {
                    selected = null
                    amount = ""
                    refreshData()
                }
            }
            throw failure
        }
        check(prefs.edit().remove(journal).commit())
        pending = null
        amount = ""
        note = ""
        if (inventory) selected = null
        refreshData()
        notice = "Registro guardado."
    }

    LaunchedEffect(journal) { run("Cargando…") { refreshData() } }
    BackHandler { if (progress.isEmpty()) onClose() }
    EmployeeLayout {
        Text(if (inventory) "Inventario" else "Fiado", style = MaterialTheme.typography.headlineSmall)
        Text(access.name)
        val item = selected
        if (pending != null) {
            Text("Hay un registro por confirmar. Consulta el resultado antes de volver a registrar.")
            Button(onClick = { record(null, null) }, enabled = progress.isEmpty()) { Text("Confirmar registro pendiente") }
        } else if (item == null) {
            if (progress.isEmpty() && rows.isEmpty() && !error) {
                Text(if (inventory) "Todavía no hay productos." else "Todavía no hay clientes de fiado.")
            }
            rows.forEach { row ->
                val stock = if (!inventory) money(row.optLong("balanceCents")) else {
                    if (row.optBoolean("unlimitedStock")) "Existencia ilimitada"
                    else qtyText(row.getInt("stockMilli"), row.getString("unit"))
                }
                OutlinedButton(
                    onClick = {
                        selected = row
                        amount = if (inventory) qtyInputText(row.getInt("stockMilli")) else ""
                        note = ""
                        if (!inventory) run("Consultando saldo…") { refreshData() }
                    },
                    enabled = progress.isEmpty() && (!inventory || !row.optBoolean("unlimitedStock")),
                    modifier = Modifier.fillMaxWidth(),
                ) { Text(row.getString("name") + " · " + stock) }
            }
            OutlinedButton(onClick = { run("Actualizando…") { refreshData() } }, enabled = progress.isEmpty()) {
                Text("Actualizar")
            }
        } else {
            Text(item.getString("name"), style = MaterialTheme.typography.titleMedium)
            if (!inventory) {
                detail?.let { Text("Saldo pendiente " + money(it.optLong("balanceCents"))) }
                OutlinedButton(onClick = { payment = !payment }, enabled = progress.isEmpty()) {
                    Text(if (payment) "Movimiento: Abono" else "Movimiento: Cargo manual")
                }
            }
            OutlinedTextField(
                value = amount, onValueChange = { amount = it }, singleLine = true,
                enabled = progress.isEmpty(),
                label = { Text(if (inventory) "Existencia contada" else "Importe en pesos") },
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                modifier = Modifier.fillMaxWidth(),
            )
            OutlinedTextField(
                value = note, onValueChange = { note = it.take(200) }, singleLine = true,
                enabled = progress.isEmpty(),
                label = { Text(if (inventory) "Motivo" else "Concepto") },
                modifier = Modifier.fillMaxWidth(),
            )
            val id = item.getString("id")
            val count = countedMilli(amount)
            val cents = parseCashCents(amount)?.takeIf { it in 1..Int.MAX_VALUE.toLong() }
            Button(
                enabled = progress.isEmpty() && note.isNotBlank() && (if (inventory) count != null else cents != null),
                onClick = {
                    if (inventory) record(JSONObject().put("stockMilli", count).put("expectedStockMilli", item.getInt("stockMilli"))
                        .put("reason", note.trim()), "$path/$id/adjust")
                    else record(JSONObject().put("amountCents", cents).put("kind", if (payment) "payment" else "charge")
                        .put("note", note.trim()), "$path/$id/entries")
                },
            ) { Text(if (inventory) "Guardar ajuste" else "Registrar movimiento") }
            OutlinedButton(onClick = { selected = null; detail = null; notice = "" }, enabled = progress.isEmpty()) {
                Text("Volver a la lista")
            }
        }
        if (progress.isNotEmpty()) {
            Text(progress)
            LinearProgressIndicator(Modifier.fillMaxWidth())
        }
        if (notice.isNotBlank()) Text(notice,
            color = if (error) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurface)
        OutlinedButton(onClick = onClose, enabled = progress.isEmpty()) { Text("Volver a mi turno") }
    }
}

@Composable
private fun EmployeeLayout(content: @Composable androidx.compose.foundation.layout.ColumnScope.() -> Unit) {
    Column(
        Modifier.fillMaxSize().safeDrawingPadding().imePadding().verticalScroll(rememberScrollState()).padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
        content = content,
    )
}
