package mx.abarpay.mobile

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Groups
import androidx.compose.material.icons.outlined.Inventory2
import androidx.compose.material.icons.outlined.Payments
import androidx.compose.material.icons.outlined.PointOfSale
import androidx.compose.material.icons.outlined.Settings
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/** Inicio del dueño: tarjetas de estado y actividades. Sin botones duplicados de pestañas. */
@Composable
internal fun HomeScreen(s: ShopState, vm: ShopViewModel, openSettings: () -> Unit) {
    val employee = s.employee
    if (employee != null && !employee.isOwner) {
        EmployeeHome(s, employee)
        return
    }
    OwnerHome(s, vm, employee, openSettings)
}

@Composable
private fun OwnerHome(s: ShopState, vm: ShopViewModel, employee: Employee?, openSettings: () -> Unit) {
    val report = s.report
    val lowStock = s.bootstrap?.products.orEmpty().filter { it.isLowStock }
    val pending = pendingInvites(s.team)
    val recent = recentAdjustments(s.inventory)
    LazyColumn(contentPadding = PaddingValues(20.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        item {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("Hola, " + (employee?.name ?: "dueño"), color = Muted, fontSize = 13.sp)
                    Title(
                        employee?.nickname?.takeIf { it.isNotBlank() }?.let { "Hola, " + it } ?: "Tu tiendita",
                    )
                }
                IconButton(
                    onClick = openSettings,
                    enabled = !s.busy,
                    modifier = Modifier.testTag("abrir-ajustes"),
                ) { Icon(Icons.Outlined.Settings, "Ajustes y conexión", tint = Purple) }
            }
        }
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                StatusCard(
                    label = "Ventas de hoy",
                    value = money(report?.totalCents ?: 0),
                    detail = (report?.salesCount ?: 0).toString() + " ventas",
                    tag = "card-ventas",
                    modifier = Modifier.weight(1f),
                )
                StatusCard(
                    label = "Fiado por cobrar",
                    value = money(report?.fiadoOutstandingCents ?: 0),
                    detail = "Saldos de clientes",
                    tag = "card-fiado",
                    modifier = Modifier.weight(1f),
                )
            }
        }
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                // Contrato v2 · tickets: los cobros por conciliar dejan de ser una
                // alarma en el teléfono y viven como rastro en la consola.
                StatusCard(
                    label = "Cobrado hoy",
                    value = money(report?.collectedCents ?: 0),
                    detail = "efectivo + PEY",
                    tag = "card-cobrado",
                    modifier = Modifier.weight(1f),
                )
                StatusCard(
                    label = "Stock bajo",
                    value = lowStock.size.toString(),
                    detail = "Productos por reponer",
                    tag = "card-stock",
                    modifier = Modifier.weight(1f),
                )
            }
        }
        if (s.employee?.canSell != false) {
            item {
                Action(
                    "Cobrar ahora",
                    Icons.Outlined.PointOfSale,
                    "Efectivo, PEY/CoDi o fiado",
                    primary = true,
                ) { vm.tab(TAB_SELL) }
            }
        }
        item {
            Panel {
                Text("Actividades", fontSize = 18.sp, fontWeight = FontWeight.Bold)
                if (lowStock.isEmpty() && pending == 0 && recent.isEmpty()) {
                    MutedText("Sin novedades por ahora. Actualiza para ver los últimos movimientos.")
                }
                lowStock.take(3).forEach { product ->
                    ActivityRow("Stock bajo", product.name + " · " + product.stockLabel)
                }
                if (pending > 0) {
                    ActivityRow(
                        "Invitaciones",
                        if (pending == 1) "1 invitación pendiente de aceptar" else pending.toString() + " invitaciones pendientes",
                    )
                }
                recent.forEach { item ->
                    val who = item.lastUpdatedByName?.let { name ->
                        name + (item.lastUpdatedByNickname?.takeIf { it.isNotBlank() }?.let { " · " + it } ?: "")
                    } ?: "Sin datos"
                    ActivityRow("Ajuste reciente", item.name + " · " + who)
                }
            }
        }
        item {
            Action(
                "Tu equipo",
                Icons.Outlined.Groups,
                "Permisos, apodos e invitaciones",
                modifier = Modifier.testTag("abrir-equipo"),
            ) { vm.openTeam() }
        }
        item { TextButton(onClick = vm::refresh, enabled = !s.busy) { Text("Actualizar información") } }
    }
}

@Composable
private fun StatusCard(label: String, value: String, detail: String, tag: String, modifier: Modifier = Modifier) {
    Card(
        modifier.testTag(tag),
        shape = RoundedCornerShape(20.dp),
        colors = CardDefaults.cardColors(containerColor = Color.White),
        elevation = CardDefaults.cardElevation(defaultElevation = 1.dp),
    ) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(3.dp)) {
            Text(label, color = Muted, fontSize = 12.sp)
            Text(value, fontWeight = FontWeight.Bold, fontSize = 20.sp)
            Text(detail, color = Muted, fontSize = 11.sp)
        }
    }
}

@Composable
private fun ActivityRow(title: String, detail: String) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        Text(title, color = Muted, fontSize = 12.sp, modifier = Modifier.width(94.dp))
        Text(detail, fontSize = 13.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
    }
}

/** Inicio del empleado: tareas sencillas y los permisos que tiene en esta tienda. */
@Composable
private fun EmployeeHome(s: ShopState, employee: Employee) {
    var countInventory by rememberSaveable { mutableStateOf(false) }
    var cleanStore by rememberSaveable { mutableStateOf(false) }
    val lowStock = s.bootstrap?.products.orEmpty().filter { it.isLowStock }
    LazyColumn(contentPadding = PaddingValues(20.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        item {
            Text("Hola, " + employee.name, color = Muted, fontSize = 13.sp)
            Title("Tus tareas de hoy")
        }
        item {
            Panel {
                Text("Tareas de la tienda", fontWeight = FontWeight.Bold)
                TaskRow("Contar inventario", countInventory, enabled = employee.canInventory) { countInventory = it }
                TaskRow("Limpiar tienda", cleanStore) { cleanStore = it }
            }
        }
        item {
            Panel {
                Text("Stock bajo", fontWeight = FontWeight.Bold)
                if (lowStock.isEmpty()) MutedText("Sin alertas de stock. Buen trabajo.")
                lowStock.take(6).forEach { product ->
                    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                        Icon(Icons.Outlined.Inventory2, null, Modifier.size(18.dp), tint = Amber)
                        Spacer(Modifier.width(10.dp))
                        Text(product.name, Modifier.weight(1f), fontSize = 14.sp)
                        Text(product.stockLabel, color = Amber, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
                    }
                }
                if (lowStock.isNotEmpty() && employee.canInventory) {
                    MutedText("Puedes contar existencias por voz desde Inventario, con el micrófono.", 12)
                }
            }
        }
        item {
            Panel {
                Text("Tus permisos", fontWeight = FontWeight.Bold)
                PermissionLine("Cobrar", employee.canSell)
                PermissionLine("Fiado", employee.canFiado)
                PermissionLine("Inventario", employee.canInventory)
                HorizontalDivider()
                InfoRow("Reportes", "Solo el dueño")
                MutedText("Si necesitas otro permiso, pídeselo al dueño desde su teléfono.", 12)
            }
        }
    }
}

@Composable
private fun TaskRow(label: String, checked: Boolean, enabled: Boolean = true, onChange: (Boolean) -> Unit) {
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Checkbox(checked, { onChange(it) }, enabled = enabled, modifier = Modifier.testTag("tarea-" + label))
        Column(Modifier.weight(1f)) {
            Text(label, fontSize = 15.sp, fontWeight = FontWeight.SemiBold)
            if (!enabled) Text("Tu perfil no tiene permiso de inventario", color = Muted, fontSize = 11.sp)
        }
    }
}

@Composable
private fun PermissionLine(label: String, allowed: Boolean) {
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Icon(
            if (allowed) Icons.Outlined.Payments else Icons.Outlined.PointOfSale,
            null,
            Modifier.size(16.dp),
            tint = if (allowed) Green else Muted,
        )
        Spacer(Modifier.width(8.dp))
        Text(label, Modifier.weight(1f), fontSize = 14.sp)
        Text(if (allowed) "Sí" else "No", fontWeight = FontWeight.Bold, color = if (allowed) Green else Muted, fontSize = 13.sp)
    }
}
