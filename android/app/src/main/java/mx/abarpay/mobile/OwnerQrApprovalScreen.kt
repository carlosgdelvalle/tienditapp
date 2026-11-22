package mx.abarpay.mobile

import android.content.Intent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
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
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import kotlinx.coroutines.launch

/**
 * Pantalla del dueño para aprobar el ingreso por QR a la consola (J-11).
 * El primer "Entrar" lanza el navegador con OwnerAuth.beginSignIn() si no hay
 * token; cuando el retorno OIDC incrementa [authRevision] se retoman las
 * membresías y se sigue al alta o al escáner. Si el navegador vuelve sin
 * retorno se limpia el estado para reintentar. Toda llamada de red corre en
 * Dispatchers.IO.
 */
@Composable
fun OwnerQrApprovalScreen(
    ownerAuth: OwnerAuth,
    apiBaseUrl: String,
    authRevision: Int,
    authError: String?,
    onApproved: (String) -> Unit,
    onClose: () -> Unit,
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf("") }
    var step by remember { mutableStateOf("ready") }

    var signupName by remember { mutableStateOf("") }
    var signupStore by remember { mutableStateOf("") }

    var pendingCode by remember { mutableStateOf("") }
    var pendingStore by remember { mutableStateOf("") }
    var pendingRaw by remember { mutableStateOf("") }
    var waitingOidc by remember { mutableStateOf(false) }
    var oidcRevisionAtClick by remember { mutableStateOf(0) }

    suspend fun proceed() {
        busy = true
        runCatching {
            val token = resolveOwnerToken(ownerAuth)
            val api = OwnerQrApi(apiBaseUrl, token)
            val tenants = kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.IO) {
                api.ownerTenantIds()
            }
            if (tenants.isEmpty()) step = "signup" else step = "scanning"
        }.onFailure { error = it.message ?: "No se pudo iniciar sesión" }
        busy = false
    }

    LaunchedEffect(authRevision) {
        if (authRevision > 0) {
            waitingOidc = false
            if (authError != null) {
                error = authError
                busy = false
            } else {
                proceed()
            }
        }
    }

    val lifecycleOwner = LocalLifecycleOwner.current
    DisposableEffect(lifecycleOwner) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME && waitingOidc && authRevision == oidcRevisionAtClick) {
                waitingOidc = false
                busy = false
                error = "No se completó el inicio de sesión. Intenta de nuevo."
            }
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose { lifecycleOwner.lifecycle.removeObserver(observer) }
    }

    if (step == "scanning") {
        ContinuousScannerScreen(
            onResult = { raw ->
                runCatching { OwnerQrParser.parse(raw) }.onSuccess { challenge ->
                    scope.launch {
                        busy = true
                        runCatching {
                            val token = resolveOwnerToken(ownerAuth)
                            val api = OwnerQrApi(apiBaseUrl, token)
                            val store = kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.IO) {
                                api.ownerStoreName()
                            }
                            pendingCode = challenge.code
                            pendingStore = store
                            pendingRaw = raw
                            step = "confirm"
                        }.onFailure {
                            error = it.message ?: "No se pudo leer la tienda"
                            step = "ready"
                        }
                        busy = false
                    }
                }.onFailure {
                    error = it.message ?: "El código no es un reto de Abarpay"
                    step = "ready"
                }
            },
            onClose = { step = "ready" },
        )
        return
    }

    Column(
        modifier = Modifier.fillMaxSize().padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        when (step) {
            "signup" -> {
                Text("Configura tu tienda", style = MaterialTheme.typography.titleLarge)
                OutlinedTextField(
                    value = signupName,
                    onValueChange = { signupName = it },
                    label = { Text("Tu nombre (dueño)") },
                    modifier = Modifier.fillMaxWidth().testTag("owner-signup-name"),
                )
                OutlinedTextField(
                    value = signupStore,
                    onValueChange = { signupStore = it },
                    label = { Text("Tu negocio") },
                    modifier = Modifier.fillMaxWidth().testTag("owner-signup-store"),
                )
                Button(
                    onClick = {
                        scope.launch {
                            busy = true
                            runCatching {
                                val token = resolveOwnerToken(ownerAuth)
                                kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.IO) {
                                    OwnerQrApi(apiBaseUrl, token).signup(signupName.trim(), signupStore.trim())
                                }
                            }.onSuccess {
                                error = ""
                                step = "ready"
                            }.onFailure { error = it.message ?: "No se pudo crear la tienda" }
                            busy = false
                        }
                    },
                    enabled = !busy && signupName.isNotBlank() && signupStore.isNotBlank(),
                    modifier = Modifier.testTag("owner-signup-submit"),
                ) {
                    Text("Empezar")
                }
            }

            "confirm" -> {
                Text("Verifica este código", style = MaterialTheme.typography.titleLarge)
                Text(pendingCode, style = MaterialTheme.typography.displayMedium)
                if (pendingStore.isNotBlank()) {
                    Text(pendingStore)
                }
                Spacer(Modifier.height(16.dp))
                Button(
                    onClick = {
                        scope.launch {
                            busy = true
                            runCatching {
                                val prepared = prepareOwnerApproval(context, ownerAuth, apiBaseUrl)
                                approveOwnerChallenge(prepared, pendingRaw)
                            }.onSuccess { onApproved(it) }.onFailure {
                                error = it.message ?: "No se pudo aprobar el reto"
                                step = "ready"
                            }
                            busy = false
                        }
                    },
                    enabled = !busy,
                    modifier = Modifier.fillMaxWidth().testTag("owner-approve"),
                ) {
                    Text("Aprobar acceso")
                }
                OutlinedButton(
                    onClick = { step = "ready" },
                    enabled = !busy,
                    modifier = Modifier.fillMaxWidth().testTag("owner-cancel"),
                ) {
                    Text("Cancelar")
                }
            }

            "done" -> {
                Text("Acceso aprobado", style = MaterialTheme.typography.titleLarge)
                Button(onClick = onClose, modifier = Modifier.testTag("owner-done-close")) {
                    Text("Cerrar")
                }
            }

            else -> {
                Text("Entra a tu tienda", style = MaterialTheme.typography.titleLarge)
                if (error.isNotBlank()) {
                    Text(error, color = MaterialTheme.colorScheme.error)
                }
                Button(
                    onClick = {
                        if (OwnerAuthSeam.tokenProvider != null || ownerAuth.accessToken() != null) {
                            scope.launch { proceed() }
                        } else {
                            busy = true
                            oidcRevisionAtClick = authRevision
                            waitingOidc = true
                            runCatching {
                                val intent = ownerAuth.beginSignIn().addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                                context.startActivity(intent)
                            }.onFailure {
                                waitingOidc = false
                                busy = false
                                error = it.message ?: "No se pudo abrir el inicio de sesión"
                            }
                        }
                    },
                    enabled = !busy && apiBaseUrl.isNotBlank(),
                    modifier = Modifier.fillMaxWidth().testTag("owner-start"),
                ) {
                    Text("Entrar a mi tienda")
                }
                if (busy) {
                    LinearProgressIndicator()
                }
            }
        }
    }
}
