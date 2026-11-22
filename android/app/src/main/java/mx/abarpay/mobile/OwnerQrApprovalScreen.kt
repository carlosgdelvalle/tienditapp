package mx.abarpay.mobile

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
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch

/**
 * Pantalla del dueño para aprobar el ingreso por QR a la consola (J-11).
 * El token se resuelve con [OwnerAuth] (OIDC real) o [OwnerAuthSeam] en pruebas.
 * Si el dueño no tiene tienda se muestra el alta; al escanear se muestra el
 * código de verificación y la tienda real de la membresía, y solo un
 * "Aprobar acceso" explícito firma y aprueba el reto. Cancelar deja el reto
 * sin aprobar. Toda llamada de red corre en Dispatchers.IO.
 */
@Composable
fun OwnerQrApprovalScreen(
    ownerAuth: OwnerAuth,
    apiBaseUrl: String,
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
                        scope.launch {
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
