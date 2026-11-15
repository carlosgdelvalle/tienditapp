package mx.abarpay.mobile

import android.content.Intent
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material.icons.outlined.PersonAdd
import androidx.compose.material.icons.outlined.Share
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/** Equipo del dueño: nombres propios, apodos, permisos y envío de invitaciones. */
@Composable
internal fun TeamScreen(s: ShopState, vm: ShopViewModel) {
    var inviteOpen by rememberSaveable { mutableStateOf(false) }
    s.invite?.let { invite ->
        InviteQrDialog(
            invite = invite,
            storeName = s.bootstrap?.store?.name.orEmpty(),
            onDismiss = vm::closeInviteDialog,
        )
    }
    LazyColumn(contentPadding = PaddingValues(20.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        item {
            TextButton(onClick = vm::closeTeam, enabled = !s.busy) {
                Icon(Icons.AutoMirrored.Outlined.ArrowBack, null, Modifier.size(18.dp))
                Spacer(Modifier.width(8.dp))
                Text("Volver al inicio")
            }
        }
        item {
            Title("Equipo")
            MutedText("Los permisos se guardan en el servidor y aplican cuando esa persona abra la app.")
        }
        if (s.team.isNullOrEmpty()) {
            item { MutedText("Todavía no hay empleados registrados.") }
        }
        items(s.team.orEmpty(), key = { it.id }) { employee ->
            EmployeeRow(employee, s.busy, vm)
        }
        item {
            Button(
                onClick = { inviteOpen = true },
                enabled = !s.busy,
                modifier = Modifier.fillMaxWidth().heightIn(min = 52.dp).testTag("invitar-empleado"),
                shape = RoundedCornerShape(16.dp),
            ) {
                Icon(Icons.Outlined.PersonAdd, null, Modifier.size(20.dp))
                Spacer(Modifier.width(8.dp))
                Text("Invitar empleado")
            }
        }
        if (inviteOpen) {
            item {
                InviteEmployeeForm(
                    busy = s.busy,
                    onDismiss = { inviteOpen = false },
                    onConfirm = { name, sell, fiado, inventory ->
                        inviteOpen = false
                        vm.createInvite(name, sell, fiado, inventory)
                    },
                )
            }
        }
        item {
            MutedText("La invitación se comparte con un enlace y un QR. La persona elige su apodo al aceptarla.", 12)
        }
    }
}

@Composable
private fun EmployeeRow(employee: Employee, busy: Boolean, vm: ShopViewModel) {
    Panel {
        Text(employee.name, fontWeight = FontWeight.Bold, fontSize = 17.sp)
        employee.nickname?.takeIf { it.isNotBlank() }?.let {
            Text("Apodo: " + it, color = Muted, fontSize = 12.sp)
        }
        Text(
            when {
                employee.isOwner -> "Dueño · todos los permisos"
                employee.active -> "Empleado activo"
                else -> "Invitación pendiente de aceptar"
            },
            color = when {
                employee.isOwner -> Purple
                employee.active -> Green
                else -> Amber
            },
            fontSize = 12.sp,
            fontWeight = FontWeight.SemiBold,
        )
        if (employee.isOwner) return@Panel
        HorizontalDivider()
        SwitchRow("Puede cobrar", employee.canSell, busy, "perm-" + employee.id + "-sell") {
            vm.patchEmployee(employee.id, canSell = it)
        }
        SwitchRow("Puede fiar", employee.canFiado, busy, "perm-" + employee.id + "-fiado") {
            vm.patchEmployee(employee.id, canFiado = it)
        }
        SwitchRow("Puede editar inventario", employee.canInventory, busy, "perm-" + employee.id + "-inventory") {
            vm.patchEmployee(employee.id, canInventory = it)
        }
        SwitchRow("Activo en la tienda", employee.active, busy, "perm-" + employee.id + "-active") {
            vm.patchEmployee(employee.id, active = it)
        }
    }
}

@Composable
private fun SwitchRow(label: String, checked: Boolean, busy: Boolean, tag: String, onChange: (Boolean) -> Unit) {
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Text(label, Modifier.weight(1f), fontSize = 14.sp)
        Switch(checked = checked, onCheckedChange = onChange, enabled = !busy, modifier = Modifier.testTag(tag))
    }
}

/** Formulario de invitación dentro de la pantalla de Equipo (sin ventanas emergentes). */
@Composable
private fun InviteEmployeeForm(
    busy: Boolean,
    onDismiss: () -> Unit,
    onConfirm: (String, Boolean, Boolean, Boolean) -> Unit,
) {
    var name by rememberSaveable { mutableStateOf("") }
    var sell by rememberSaveable { mutableStateOf(true) }
    var fiado by rememberSaveable { mutableStateOf(true) }
    var inventory by rememberSaveable { mutableStateOf(false) }
    Panel {
        Text("Invitar empleado", fontWeight = FontWeight.Bold, fontSize = 17.sp)
        Text("Ponle su nombre propio; el apodo lo elige la persona al aceptar.", fontSize = 12.sp, color = Muted)
        OutlinedTextField(
            name, { name = it },
            Modifier.fillMaxWidth().testTag("invite-name"),
            label = { Text("Nombre de la persona") },
            singleLine = true,
            enabled = !busy,
            shape = RoundedCornerShape(16.dp),
        )
        HorizontalDivider()
        SwitchRow("Puede cobrar", sell, busy, "invite-canSell") { sell = it }
        SwitchRow("Puede fiar", fiado, busy, "invite-canFiado") { fiado = it }
        SwitchRow("Puede editar inventario", inventory, busy, "invite-canInventory") { inventory = it }
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Button(
                onClick = { onConfirm(name, sell, fiado, inventory) },
                enabled = name.isNotBlank() && !busy,
                modifier = Modifier.weight(1f).heightIn(min = 50.dp).testTag("crear-invitacion"),
                shape = RoundedCornerShape(16.dp),
            ) { Text("Crear invitación") }
            TextButton(onClick = onDismiss, enabled = !busy) { Text("Cancelar") }
        }
    }
}

@Composable
private fun InviteQrDialog(invite: Invite, storeName: String, onDismiss: () -> Unit) {
    val qr = rememberInviteQr(invite.url)
    val context = LocalContext.current
    fun share() {
        val send = Intent(Intent.ACTION_SEND).apply {
            type = "text/plain"
            putExtra(Intent.EXTRA_SUBJECT, "Invitación a Abarpay")
            putExtra(
                Intent.EXTRA_TEXT,
                "Únete al equipo de " + (storeName.ifBlank { "la tienda" }) + " en Abarpay: " + invite.url,
            )
        }
        runCatching { context.startActivity(Intent.createChooser(send, "Compartir invitación")) }
    }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Comparte la invitación") },
        text = {
            Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(10.dp)) {
                if (qr != null) {
                    Image(
                        qr,
                        "QR de la invitación",
                        Modifier.fillMaxWidth(0.8f).aspectRatio(1f).padding(4.dp),
                    )
                } else {
                    Text("No pudimos dibujar el QR. Comparte el enlace de abajo.", color = Amber)
                }
                Text(
                    invite.url,
                    fontSize = 12.sp,
                    color = Muted,
                    modifier = Modifier.testTag("invite-url"),
                )
                Text("La invitación vence en 7 días y solo se puede aceptar una vez.", fontSize = 12.sp)
            }
        },
        confirmButton = {
            TextButton(onClick = { share() }, modifier = Modifier.testTag("compartir-invitacion")) {
                Icon(Icons.Outlined.Share, null, Modifier.size(18.dp))
                Spacer(Modifier.width(8.dp))
                Text("Compartir enlace")
            }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Listo") } },
    )
}

/** Pantalla que abre el enlace abarpay://empleado/<token> o el enlace HTTPS. */
@Composable
internal fun InviteAcceptScreen(s: ShopState, vm: ShopViewModel) {
    var nickname by rememberSaveable { mutableStateOf("") }
    val info = s.inviteInfo
    LazyColumn(contentPadding = PaddingValues(20.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        item {
            Title(if (info != null) "Ponle tu apodo" else "Abrimos tu invitación…")
            MutedText(
                if (info != null) "Así te verán el dueño y tus compañeros en Abarpay."
                else "Estamos revisando la invitación con el servidor.",
            )
        }
        when {
            info != null -> {
                item {
                    Panel {
                        Text(info.storeName.ifBlank { "La tienda" }, fontSize = 20.sp, fontWeight = FontWeight.Bold)
                        if (info.businessType.isNotBlank()) {
                            Text(info.businessType, color = Muted, fontSize = 13.sp)
                        }
                        HorizontalDivider()
                        Text("La invitación es para " + info.name + ".", fontSize = 14.sp)
                        InfoRow("Puede cobrar", if (info.canSell) "Sí" else "No")
                        InfoRow("Puede fiar", if (info.canFiado) "Sí" else "No")
                        InfoRow("Puede editar inventario", if (info.canInventory) "Sí" else "No")
                        InfoRow("Reportes", "Solo el dueño")
                    }
                }
                item {
                    OutlinedTextField(
                        nickname, { nickname = it },
                        Modifier.fillMaxWidth().testTag("invite-nickname"),
                        label = { Text("¿Cómo te dicen en la tienda?") },
                        singleLine = true,
                        enabled = !s.busy,
                        shape = RoundedCornerShape(16.dp),
                    )
                }
                item {
                    Button(
                        onClick = { vm.acceptInvite(nickname) },
                        enabled = nickname.isNotBlank() && !s.busy,
                        modifier = Modifier.fillMaxWidth().heightIn(min = 56.dp).testTag("aceptar-invitacion"),
                        shape = RoundedCornerShape(16.dp),
                    ) { Text("Aceptar invitación", fontSize = 17.sp) }
                }
                item { MutedText("Tu perfil queda ligado a este teléfono. Si cambias de teléfono, pide otra invitación.", 12) }
                item { TextButton(onClick = vm::dismissInvite, enabled = !s.busy) { Text("Ahora no") } }
            }
            s.inviteError != null -> {
                item { Notice(s.inviteError, true) }
                item {
                    Button(onClick = vm::retryInvite, enabled = !s.busy, modifier = Modifier.fillMaxWidth()) {
                        Text("Reintentar")
                    }
                }
                item { TextButton(onClick = vm::dismissInvite) { Text("Volver") } }
            }
            else -> item {
                OutlinedButton(onClick = vm::dismissInvite, enabled = !s.busy) { Text("Volver") }
            }
        }
    }
}
