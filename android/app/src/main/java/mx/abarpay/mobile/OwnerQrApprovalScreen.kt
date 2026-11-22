package mx.abarpay.mobile

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
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
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

@Composable
fun OwnerQrApprovalScreen(
    ownerAuth: OwnerAuth,
    apiBaseUrl: String,
    onClose: () -> Unit,
    startInCash: Boolean = false,
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var step by rememberSaveable { mutableStateOf("ready") }
    var phone by rememberSaveable { mutableStateOf("") }
    var challengeId by rememberSaveable { mutableStateOf("") }
    var resendAt by rememberSaveable { mutableStateOf(0L) }
    var signupName by rememberSaveable { mutableStateOf("") }
    var signupStore by rememberSaveable { mutableStateOf("") }
    var rawQr by rememberSaveable { mutableStateOf("") }
    var code by remember { mutableStateOf("") }
    var resendSeconds by remember { mutableStateOf(0) }
    var error by remember { mutableStateOf("") }
    var working by remember { mutableStateOf("") }
    var stores by remember { mutableStateOf(emptyList<OwnerStore>()) }
    var selectedId by rememberSaveable { mutableStateOf("") }

    suspend fun ownerApi(): OwnerQrApi {
        val token = ownerAuth.accessToken()
            ?: throw IllegalStateException("Vuelve a entrar con tu celular.")
        return OwnerQrApi(apiBaseUrl, token)
    }

    suspend fun openStore() {
        val token = ownerAuth.accessToken()
        if (token == null) {
            step = "phone"
            return
        }
        stores = withContext(Dispatchers.IO) { OwnerQrApi(apiBaseUrl, token).ownerStores() }
        step = when {
            stores.isEmpty() -> "signup"
            startInCash -> "cash"
            else -> "scanReady"
        }
    }

    fun runAction(message: String, action: suspend () -> Unit) {
        if (working.isNotEmpty()) return
        error = ""
        working = message
        scope.launch {
            try {
                action()
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (failure: ApiFailure) {
                error = failure.message.orEmpty()
            } catch (_: Exception) {
                error = "No se pudo completar. Revisa tu conexión e intenta de nuevo."
            } finally {
                working = ""
            }
        }
    }

    fun sendCode() = runAction("Enviando SMS…") {
        challengeId = ownerAuth.startEnrollment(phone)
        code = ""
        resendAt = android.os.SystemClock.elapsedRealtime() + 30_000
        step = "code"
    }

    fun goBack() {
        if (working.isNotEmpty()) return
        error = ""
        when (step) {
            "code" -> { code = ""; step = "phone" }
            "confirm", "scanning" -> { rawQr = ""; step = "scanReady" }
            else -> onClose()
        }
    }

    LaunchedEffect(resendAt) {
        do {
            resendSeconds = ((resendAt - android.os.SystemClock.elapsedRealtime() + 999) / 1000)
                .toInt().coerceAtLeast(0)
            if (resendSeconds > 0) delay(500)
        } while (resendSeconds > 0)
    }

    // An activity recreation can restore the confirmation but not the cached membership.
    LaunchedEffect(step) {
        if (step in setOf("confirm", "cash") && stores.isEmpty()) {
            runAction("Cargando tu tienda…") {
                val api = ownerApi()
                stores = withContext(Dispatchers.IO) { api.ownerStores() }
            }
        }
    }

    if (step == "cash") {
        val selected = stores.singleOrNull() ?: stores.find { it.tenantId == selectedId }
        if (selected != null) {
            OwnerCashScreen(ownerAuth, apiBaseUrl, selected, onClose)
            return
        }
    }

    if (step == "scanning") {
        ContinuousScannerScreen(
            onResult = { raw ->
                val qr = runCatching { OwnerQrParser.parse(raw) }.getOrNull()
                if (qr == null || qr.intent != "browser_login") {
                    step = "scanReady"
                    error = "Escanea el código de acceso de la consola de Abarpay."
                } else {
                    rawQr = raw
                    selectedId = stores.singleOrNull()?.tenantId.orEmpty()
                    step = "confirm"
                }
            },
            onClose = { step = "scanReady" },
        )
        return
    }

    BackHandler(onBack = ::goBack)
    val idle = working.isEmpty()
    Column(
        modifier = Modifier.fillMaxSize().imePadding().verticalScroll(rememberScrollState()).padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        when (step) {
            "phone" -> {
                Text("¿Cuál es tu número de celular?", style = MaterialTheme.typography.headlineSmall)
                Text("Te enviaremos un código por SMS para vincular este celular.")
                OutlinedTextField(
                    value = phone,
                    onValueChange = { phone = it.filter { c -> c in '0'..'9' }.take(10) },
                    label = { Text("Número de celular") },
                    prefix = { Text("+52 ") },
                    singleLine = true,
                    enabled = idle,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Phone),
                    modifier = Modifier.fillMaxWidth().testTag("owner-phone"),
                )
                Button(onClick = ::sendCode, enabled = idle && phone.length == 10,
                    modifier = Modifier.fillMaxWidth().testTag("owner-send-code")) { Text("Enviar código") }
            }
            "code" -> {
                Text("Escribe el código del SMS", style = MaterialTheme.typography.headlineSmall)
                Text("Lo enviamos a +52 $phone. Puedes salir a revisar tus mensajes y volver aquí.")
                OutlinedTextField(
                    value = code,
                    onValueChange = { code = it.filter { c -> c in '0'..'9' }.take(6) },
                    label = { Text("Código de 6 dígitos") },
                    singleLine = true,
                    enabled = idle,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                    modifier = Modifier.fillMaxWidth().testTag("owner-code"),
                )
                Button(
                    onClick = {
                        runAction("Verificando tu celular…") {
                            ownerAuth.verifyEnrollment(challengeId, code)
                            code = ""
                            openStore()
                        }
                    },
                    enabled = idle && code.length == 6,
                    modifier = Modifier.fillMaxWidth().testTag("owner-verify"),
                ) { Text("Verificar mi celular") }
                TextButton(onClick = ::sendCode, enabled = idle && resendSeconds == 0) {
                    Text(if (resendSeconds > 0) "Puedes reenviar en ${resendSeconds} s" else "Reenviar código")
                }
            }
            "signup" -> {
                Text("Configura tu tienda", style = MaterialTheme.typography.headlineSmall)
                OutlinedTextField(
                    value = signupName, onValueChange = { signupName = it },
                    label = { Text("Tu nombre") }, singleLine = true, enabled = idle,
                    modifier = Modifier.fillMaxWidth().testTag("owner-signup-name"),
                )
                OutlinedTextField(
                    value = signupStore, onValueChange = { signupStore = it },
                    label = { Text("Nombre de tu negocio") }, singleLine = true, enabled = idle,
                    modifier = Modifier.fillMaxWidth().testTag("owner-signup-store"),
                )
                Button(
                    onClick = {
                        runAction("Creando tu tienda…") {
                            val api = ownerApi()
                            withContext(Dispatchers.IO) { api.signup(signupName.trim(), signupStore.trim()) }
                            openStore()
                        }
                    },
                    enabled = idle && signupName.isNotBlank() && signupStore.isNotBlank(),
                    modifier = Modifier.fillMaxWidth().testTag("owner-signup-submit"),
                ) { Text("Crear mi tienda") }
            }
            "scanReady" -> {
                Text("Abre la consola", style = MaterialTheme.typography.headlineSmall)
                Text("Abre Abarpay en tu computadora y escanea el código que aparece ahí.")
                Button(onClick = { error = ""; step = "scanning" },
                    modifier = Modifier.fillMaxWidth().testTag("owner-scan")) { Text("Escanear código QR") }
            }
            "confirm" -> {
                val qr = remember(rawQr) { OwnerQrParser.parse(rawQr) }
                Text("¿Es el mismo código que ves en tu computadora?", style = MaterialTheme.typography.headlineSmall)
                Text(qr.code, style = MaterialTheme.typography.displayMedium)
                if (stores.size > 1) {
                    Text("Elige la tienda que quieres abrir.")
                    stores.forEach { store ->
                        OutlinedButton(onClick = { selectedId = store.tenantId }, enabled = idle) {
                            Text(if (store.tenantId == selectedId) "Elegida: ${store.name}" else store.name)
                        }
                    }
                }
                val selected = stores.singleOrNull() ?: stores.find { it.tenantId == selectedId }
                if (selected != null) Text("Tienda: ${selected.name}")
                Button(
                    onClick = {
                        runAction("Aprobando el acceso…") {
                            if (selected != null) {
                                approveOwnerChallenge(context, ownerApi(), qr, selected.tenantId)
                                rawQr = ""
                                step = "done"
                            }
                        }
                    },
                    enabled = idle && selected != null,
                    modifier = Modifier.fillMaxWidth().testTag("owner-approve"),
                ) { Text("Sí, abrir la consola") }
            }
            "done" -> {
                Text("Acceso aprobado", style = MaterialTheme.typography.headlineSmall)
                Text("Continúa en tu computadora.")
            }
            "cash" -> {
                Text("Elige la tienda donde vas a cobrar.", style = MaterialTheme.typography.headlineSmall)
                stores.forEach { store ->
                    Button(onClick = { selectedId = store.tenantId }) { Text(store.name) }
                }
                if (stores.isEmpty() && idle) {
                    OutlinedButton(onClick = { runAction("Cargando tu tienda…") { openStore() } }) {
                        Text("Volver a cargar")
                    }
                }
            }
            else -> {
                Text("Entra a tu tienda", style = MaterialTheme.typography.headlineSmall)
                Button(onClick = { runAction("Abriendo tu tienda…") { openStore() } }, enabled = idle,
                    modifier = Modifier.fillMaxWidth().testTag("owner-start")) { Text("Entrar a mi tienda") }
            }
        }

        if (!idle) {
            Text(working)
            LinearProgressIndicator(modifier = Modifier.fillMaxWidth())
        }
        if (error.isNotBlank()) Text(error, color = MaterialTheme.colorScheme.error)
        OutlinedButton(onClick = ::goBack, enabled = idle, modifier = Modifier.fillMaxWidth()) {
            Text(when (step) {
                "code" -> "Cambiar número"
                "confirm" -> "Cancelar"
                "done" -> "Cerrar"
                else -> "Volver"
            })
        }
    }
}
