package mx.abarpay.mobile

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/** Presentation-only access: fixed fictional values, no passwords, sessions, network or OAuth. */
@Composable internal fun AccessMockups(state: ShopState, enter: (Employee) -> Unit) {
    check(state.simulated)
    var register by rememberSaveable { mutableStateOf(false) }
    var owner by rememberSaveable { mutableStateOf(true) }
    var dialog by rememberSaveable { mutableStateOf<String?>(null) }
    val person = state.bootstrap?.employees?.firstOrNull { it.role == if (owner) "owner" else "employee" }
    BackHandler(enabled = register) { register = false; dialog = null }

    dialog?.let { title ->
        AlertDialog(onDismissRequest = { dialog = null }, title = { Text(title) }, text = {
            Text(if (title == "Registro simulado")
                "No se creó una cuenta ni una tienda. Abriremos la Tiendita de la Esquina con el perfil ficticio del dueño."
            else "No conectamos con $title ni verificamos una identidad. Solo abriremos el perfil de ejemplo elegido.")
        }, confirmButton = { TextButton(onClick = { dialog = null; person?.let(enter) }, enabled = person != null && !state.busy) { Text("Continuar en simulación") } },
            dismissButton = { TextButton(onClick = { dialog = null }) { Text("Volver") } })
    }

    LazyColumn(contentPadding = PaddingValues(20.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        if (register) item {
            TextButton(onClick = { register = false }) {
                Icon(Icons.AutoMirrored.Outlined.ArrowBack, null, Modifier.size(18.dp))
                Spacer(Modifier.width(8.dp)); Text("Volver al login")
            }
        }
        item {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(14.dp)) {
                Surface(shape = RoundedCornerShape(20.dp), color = Color(0xFFEADFFF)) {
                    Icon(Icons.Outlined.Storefront, null, Modifier.padding(14.dp).size(34.dp), tint = MaterialTheme.colorScheme.primary)
                }
                Column(Modifier.weight(1f)) {
                    Text(if (register) "Tu tiendita empieza aquí" else "Tu tienda, contigo", fontSize = 25.sp, fontWeight = FontWeight.Bold)
                    Text("Cobros, inventario y equipo", fontSize = 13.sp, color = Color(0xFF666680))
                }
            }
        }
        item {
            Text(if (register) "Crear cuenta" else "Iniciar sesión", fontSize = 27.sp, fontWeight = FontWeight.Bold)
            Text("MOCKUP · Datos ficticios. No escribas credenciales reales.", fontSize = 12.sp, color = Color(0xFF666680))
        }
        if (!register) item {
            Text("Elige un perfil para explorar", fontSize = 13.sp)
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                FilterChip(selected = owner, onClick = { owner = true }, label = { Text("Soy dueño") }, leadingIcon = { Icon(Icons.Outlined.Storefront, null, Modifier.size(18.dp)) })
                FilterChip(selected = !owner, onClick = { owner = false }, label = { Text("Soy empleado") }, leadingIcon = { Icon(Icons.Outlined.Badge, null, Modifier.size(18.dp)) })
            }
        }
        if (register) {
            item { MockField("Nombre del dueño", "Dueña de ejemplo", Icons.Outlined.Person) }
            item { MockField("Nombre de tu tienda", "Tiendita de la Esquina", Icons.Outlined.Storefront) }
        }
        item { MockField("Correo de ejemplo", if (owner) "duena@tiendita.example" else "empleado@tiendita.example", Icons.Outlined.MailOutline) }
        item { MockField("Contraseña de ejemplo", "DEMO-SIN-CLAVE", Icons.Outlined.Lock, password = true) }
        if (!owner && !register) item {
            MockField("Invitación de tu dueño", "TIENDITA-DEMO", Icons.Outlined.ConfirmationNumber)
            Text("Código ficticio. La invitación real y los permisos todavía no están implementados.", fontSize = 12.sp)
        }
        item {
            Button(onClick = { if (register) dialog = "Registro simulado" else person?.let(enter) },
                enabled = person != null && !state.busy, modifier = Modifier.fillMaxWidth().heightIn(min = 56.dp), shape = RoundedCornerShape(16.dp)) {
                Text(if (register) "Simular registro de mi tienda" else "Entrar en simulación", fontSize = 16.sp)
            }
            Text(if (register) "No se guardan datos ni se crean cuentas. Después podrás explorar el ejemplo del dueño."
                else "Este acceso no autentica. Solo abre la demostración sin conexión.", fontSize = 12.sp, modifier = Modifier.padding(top = 8.dp))
        }
        if (!register) {
            item {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    HorizontalDivider(Modifier.weight(1f)); Text("O prueba estos accesos", fontSize = 12.sp); HorizontalDivider(Modifier.weight(1f))
                }
            }
            item {
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    OutlinedButton(onClick = { dialog = "Google" }, modifier = Modifier.weight(1f), enabled = !state.busy, shape = RoundedCornerShape(14.dp)) { Text("Google · demo") }
                    OutlinedButton(onClick = { dialog = "Apple" }, modifier = Modifier.weight(1f), enabled = !state.busy, shape = RoundedCornerShape(14.dp)) { Text("Apple · demo") }
                }
            }
            item {
                TextButton(onClick = { owner = true; register = true }, modifier = Modifier.fillMaxWidth()) { Text("¿Tienes una tienda? Crear cuenta demo") }
            }
        } else item {
            Surface(color = Color(0xFFEADFFF), shape = RoundedCornerShape(18.dp)) {
                Row(Modifier.padding(16.dp), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    Icon(Icons.Outlined.Group, null)
                    Text("El dueño dará acceso a su equipo desde la app. Este registro solo muestra el recorrido; no crea una tienda ni invita empleados.", fontSize = 13.sp)
                }
            }
        }
    }
}

@Composable private fun MockField(label: String, value: String, icon: ImageVector, password: Boolean = false) {
    // Read-only fixture prevents accidentally collecting or retaining a real password in a demo.
    OutlinedTextField(value, {}, Modifier.fillMaxWidth(), label = { Text(label) }, readOnly = true,
        singleLine = true, shape = RoundedCornerShape(16.dp), leadingIcon = { Icon(icon, null) },
        visualTransformation = if (password) PasswordVisualTransformation() else VisualTransformation.None)
}
