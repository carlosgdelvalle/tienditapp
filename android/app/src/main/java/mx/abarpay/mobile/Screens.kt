package mx.abarpay.mobile

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material.icons.outlined.AccountBalanceWallet
import androidx.compose.material.icons.outlined.AddCircleOutline
import androidx.compose.material.icons.outlined.BarChart
import androidx.compose.material.icons.outlined.Inventory2
import androidx.compose.material.icons.outlined.People
import androidx.compose.material.icons.outlined.PersonAdd
import androidx.compose.material.icons.outlined.PointOfSale
import androidx.compose.material.icons.outlined.RemoveCircleOutline
import androidx.compose.material.icons.outlined.Search
import androidx.compose.material.icons.outlined.WarningAmber
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

@Composable
internal fun HomeScreen(s: ShopState, vm: ShopViewModel) {
    val report = s.report
    val products = s.bootstrap?.products.orEmpty()
    val lowStock = products.count { it.stockMilli <= it.lowStockMilli }
    LazyColumn(contentPadding = PaddingValues(20.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        item { Text("Hola, ${s.employee?.name.orEmpty()}", color = Muted) }
        item { Title(s.bootstrap?.store?.name ?: "Tiendita de la Esquina") }
        item {
            Action(
                title = "Cobrar ahora",
                icon = Icons.Outlined.PointOfSale,
                subtitle = "Efectivo, PEY/CoDi o fiado",
                primary = true,
            ) { vm.tab("Cobrar") }
        }
        item {
            Panel {
                Text("Ventas de hoy", fontSize = 15.sp)
                Text(money(report?.totalCents ?: 0), fontSize = 34.sp, fontWeight = FontWeight.Bold)
                Text(
                    "${report?.salesCount ?: 0} ventas · cobrado ${money(report?.collectedCents ?: 0)}",
                    color = Green,
                    fontSize = 13.sp,
                )
                HorizontalDivider()
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    Stat("Efectivo", money(report?.cashCents ?: 0), Modifier.weight(1f))
                    Stat("PEY", money(report?.peyCents ?: 0), Modifier.weight(1f))
                    Stat("Fiado", money(report?.fiadoCents ?: 0), Modifier.weight(1f))
                }
                InfoRow("Fiado por cobrar", money(report?.fiadoOutstandingCents ?: 0), strong = true)
                if ((report?.pending ?: 0) > 0) {
                    Text("${report?.pending} cobro(s) PEY por conciliar", color = Amber, fontSize = 13.sp)
                }
            }
        }
        item {
            Action("Fiado de clientes", Icons.Outlined.AccountBalanceWallet, "Saldos y abonos") { vm.tab("Fiado") }
        }
        item {
            Action(
                "Inventario",
                Icons.Outlined.Inventory2,
                if (lowStock > 0) "$lowStock producto(s) con stock bajo" else "Productos y existencias",
            ) { vm.tab("Inventario") }
        }
        item { Action("Reportes", Icons.Outlined.BarChart, "Hoy por forma de pago") { vm.tab("Reportes") } }
        item { TextButton(onClick = vm::refresh, enabled = !s.busy) { Text("Actualizar información") } }
    }
}

@Composable
private fun Stat(label: String, value: String, modifier: Modifier = Modifier) {
    Column(modifier) {
        Text(label, color = Muted, fontSize = 11.sp)
        Text(value, fontSize = 16.sp, fontWeight = FontWeight.Bold)
    }
}

@Composable
internal fun InventoryScreen(s: ShopState, vm: ShopViewModel) {
    var query by rememberSaveable { mutableStateOf("") }
    val products = s.bootstrap?.products.orEmpty().filter { it.name.contains(query, ignoreCase = true) }
    LazyColumn(contentPadding = PaddingValues(20.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        item { Title("Inventario") }
        item {
            MutedText("Ajuste simple: una unidad (1000 milli) por toque. Cada cambio queda registrado en el servidor.")
        }
        item {
            OutlinedTextField(
                query, { query = it },
                Modifier.fillMaxWidth(),
                placeholder = { Text("Buscar producto") },
                leadingIcon = { Icon(Icons.Outlined.Search, null) },
                singleLine = true,
                shape = RoundedCornerShape(28.dp),
            )
        }
        if (products.isEmpty()) item { Text("No encontramos productos con ese nombre.") }
        items(products, key = { it.id }) { p ->
            val low = p.stockMilli <= p.lowStockMilli
            Panel {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text(p.name, fontWeight = FontWeight.Bold)
                        Text("${money(p.priceCents)} · ${qtyText(1000, p.unit)}", color = Muted, fontSize = 12.sp)
                        Text(
                            "Stock: ${qtyText(p.stockMilli, p.unit)} · ${p.stockMilli} milli",
                            color = if (low) Amber else Muted,
                            fontSize = 12.sp,
                        )
                    }
                    IconButton(onClick = { vm.adjust(p.id, -1000) }, enabled = !s.busy) {
                        Icon(Icons.Outlined.RemoveCircleOutline, "Restar una unidad de ${p.name}")
                    }
                    IconButton(onClick = { vm.adjust(p.id, 1000) }, enabled = !s.busy) {
                        Icon(Icons.Outlined.AddCircleOutline, "Sumar una unidad de ${p.name}")
                    }
                }
            }
        }
        item { TextButton(onClick = vm::refresh, enabled = !s.busy) { Text("Actualizar inventario") } }
    }
}

@Composable
internal fun ReportsScreen(s: ShopState, vm: ShopViewModel) {
    val r = s.report
    if (r == null) {
        Column(Modifier.padding(24.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
            Title("Reporte no disponible")
            Text("No recibimos los datos del servidor. No sabemos el total de hoy.")
            OutlinedButton(onClick = vm::refresh, enabled = !s.busy) { Text("Reintentar") }
        }
        return
    }
    LazyColumn(contentPadding = PaddingValues(20.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        item { Title("Reportes · hoy") }
        item { MutedText("Día de la tienda: Ciudad de México") }
        item {
            Panel {
                Text("Venta total del día")
                Text(money(r.totalCents), fontSize = 36.sp, fontWeight = FontWeight.Bold)
                Text("Cobrado: ${money(r.collectedCents)}", color = Green, fontWeight = FontWeight.Bold)
                HorizontalDivider()
                InfoRow("Efectivo", money(r.cashCents))
                InfoRow("PEY / CoDi", money(r.peyCents))
                InfoRow("Fiado", money(r.fiadoCents))
                InfoRow("Fiado por cobrar", money(r.fiadoOutstandingCents))
                HorizontalDivider()
                InfoRow("Ventas", "${r.salesCount}")
                InfoRow("Cobros por conciliar", "${r.pending}")
            }
        }
        if (r.pending > 0) {
            item { Notice("${r.pending} cobro(s) por conciliar. Revísalos antes de cerrar caja.", true) }
        }
        item {
            Panel {
                Text("Por persona", fontWeight = FontWeight.Bold)
                if (r.byEmployee.isEmpty()) Text("Aún no hay ventas del día.")
                r.byEmployee.forEach {
                    val label = if (it.salesCount > 0) "${it.name} · ${it.salesCount} ventas" else it.name
                    InfoRow(label, money(it.totalCents))
                }
            }
        }
        item {
            Panel {
                Text("Productos más vendidos", fontWeight = FontWeight.Bold)
                if (r.topProducts.isEmpty()) Text("Los verás después de confirmar ventas.")
                r.topProducts.forEach { top ->
                    val unit = s.bootstrap?.products?.firstOrNull { it.id == top.productId }?.unit ?: top.unit
                    InfoRow(top.name, qtyText(top.qtyMilli, unit))
                }
            }
        }
        item {
            Panel {
                Text("Stock bajo", fontWeight = FontWeight.Bold)
                if (r.lowStock.isEmpty()) Text("Sin alertas de stock.")
                r.lowStock.forEach { InfoRow(it.name, qtyText(it.stockMilli, it.unit)) }
            }
        }
        if (r.demoMode) item { Notice("MODO DEMO · El servidor cobra PEY a $0.01 MXN", true) }
        item { TextButton(onClick = vm::refresh, enabled = !s.busy) { Text("Actualizar reporte") } }
    }
}

@Composable
internal fun FiadoScreen(s: ShopState, vm: ShopViewModel) {
    val detail = s.customerDetail
    if (detail != null) {
        CustomerDetailScreen(s, vm, detail)
        return
    }
    var query by rememberSaveable { mutableStateOf("") }
    var adding by rememberSaveable { mutableStateOf(false) }
    val customers = s.customers.filter {
        it.name.contains(query, ignoreCase = true) || it.phone?.contains(query, ignoreCase = true) == true
    }
    if (adding) {
        AddCustomerDialog(
            onDismiss = { adding = false },
            onConfirm = { name, phone ->
                adding = false
                vm.addCustomer(name, phone)
            },
        )
    }
    LazyColumn(contentPadding = PaddingValues(20.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        item { Title("Fiado") }
        item { MutedText("Ventas a crédito de clientes conocidos. El saldo lo calcula el servidor.") }
        item {
            OutlinedButton(onClick = { adding = true }, enabled = !s.busy, modifier = Modifier.fillMaxWidth()) {
                Icon(Icons.Outlined.PersonAdd, null)
                Spacer(Modifier.width(8.dp))
                Text("Agregar cliente")
            }
        }
        item {
            OutlinedTextField(
                query, { query = it },
                Modifier.fillMaxWidth(),
                placeholder = { Text("Buscar cliente") },
                leadingIcon = { Icon(Icons.Outlined.Search, null) },
                singleLine = true,
                shape = RoundedCornerShape(28.dp),
            )
        }
        if (customers.isEmpty()) item { Text("No hay clientes registrados todavía.") }
        items(customers, key = { it.id }) { c ->
            Action(
                title = c.name,
                icon = Icons.Outlined.AccountBalanceWallet,
                subtitle = (c.phone?.plus(" · ") ?: "") + "Saldo " + money(c.balanceCents),
            ) { vm.openCustomer(c.id) }
        }
        item { TextButton(onClick = vm::refresh, enabled = !s.busy) { Text("Actualizar clientes") } }
    }
}

@Composable
private fun CustomerDetailScreen(s: ShopState, vm: ShopViewModel, detail: CustomerDetail) {
    var amount by rememberSaveable { mutableStateOf("") }
    var note by rememberSaveable { mutableStateOf("") }
    val cents = parseCashCents(amount)
    LazyColumn(contentPadding = PaddingValues(20.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        item {
            TextButton(onClick = vm::closeCustomer) {
                Icon(Icons.AutoMirrored.Outlined.ArrowBack, null, Modifier.size(18.dp))
                Spacer(Modifier.width(8.dp))
                Text("Volver a fiado")
            }
        }
        item { Title(detail.customer.name) }
        item {
            Panel {
                Text("Saldo pendiente")
                Text(
                    money(detail.customer.balanceCents),
                    fontSize = 36.sp,
                    fontWeight = FontWeight.Bold,
                    color = if (detail.customer.balanceCents > 0) Amber else Green,
                )
                detail.customer.phone?.let { InfoRow("Teléfono", it) }
                Text("Los abonos reducen el saldo y quedan registrados en el servidor.", color = Muted, fontSize = 12.sp)
            }
        }
        item { SectionLabel("Abono") }
        item {
            OutlinedTextField(
                amount, { amount = it },
                Modifier.fillMaxWidth().testTag("abono-monto"),
                label = { Text("Monto en pesos") },
                placeholder = { Text("Ej. 50.00") },
                singleLine = true,
                enabled = !s.busy,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                shape = RoundedCornerShape(16.dp),
            )
        }
        item {
            OutlinedTextField(
                note, { note = it },
                Modifier.fillMaxWidth(),
                label = { Text("Nota (opcional)") },
                singleLine = true,
                enabled = !s.busy,
                shape = RoundedCornerShape(16.dp),
            )
        }
        item {
            Button(
                onClick = { cents?.let { vm.abono(it, note) } },
                enabled = cents != null && cents > 0 && !s.busy,
                modifier = Modifier.fillMaxWidth().heightIn(min = 52.dp),
                shape = RoundedCornerShape(16.dp),
            ) { Text("Registrar abono") }
        }
        item { SectionLabel("Movimientos") }
        if (detail.entries.isEmpty()) item { MutedText("Sin movimientos todavía.") }
        items(detail.entries.sortedByDescending { it.createdAt }, key = { it.id }) { entry ->
            val charge = entry.kind == "charge"
            Panel {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text(if (charge) "Cargo por venta" else "Abono", fontWeight = FontWeight.SemiBold)
                        entry.note?.let { Text(it, color = Muted, fontSize = 12.sp) }
                        entry.saleId?.let { Text(it, color = Muted, fontSize = 11.sp) }
                    }
                    Text(
                        (if (charge) "+" else "−") + money(entry.amountCents),
                        fontWeight = FontWeight.Bold,
                        color = if (charge) Purple else Green,
                    )
                }
            }
        }
    }
}

@Composable
internal fun SettingsScreen(s: ShopState, vm: ShopViewModel, close: () -> Unit) {
    val canChange = s.sale == null && !s.uncertain && !s.busy
    LazyColumn(contentPadding = PaddingValues(20.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        item { Title("Ajustes") }
        item {
            Panel {
                Text("Modo actual", fontWeight = FontWeight.Bold)
                Text(if (s.simulated) "SIMULADO · sin red y sin dinero real" else "API · ${s.server}")
                if (s.bootstrap?.demoMode == true) {
                    Text("MODO DEMO del servidor: PEY cobra $0.01 MXN", color = Amber, fontWeight = FontWeight.Bold)
                }
                Text(
                    "Sin claves de PEY, OpenAI ni OAuth en el APK. La app solo habla con tu servidor.",
                    color = Muted,
                    fontSize = 12.sp,
                )
            }
        }
        if (s.simulated && s.employee != null) {
            item {
                OutlinedButton(
                    onClick = { vm.leaveMockProfile(); close() },
                    enabled = canChange && s.cart.isEmpty(),
                    modifier = Modifier.fillMaxWidth(),
                ) { Text("Volver al login simulado") }
                if (s.cart.isNotEmpty()) Text("Termina o vacía el carrito antes de cambiar de perfil.", fontSize = 12.sp)
            }
        }
        item { SectionLabel("Servidor fijado para la demo") }
        item {
            OutlinedTextField(
                BuildConfig.DEMO_SERVER, {},
                Modifier.fillMaxWidth(),
                label = { Text("Dirección del servidor (fija)") },
                supportingText = { Text("Configuración de esta demo; no editable desde el APK.") },
                singleLine = true,
                readOnly = true,
                enabled = canChange,
            )
        }
        item {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Checkbox(true, {}, enabled = false)
                Text(
                    "Servidor de demo aprobado. Los cobros PEY son reales por $0.01 y la API no tiene control de acceso.",
                    fontSize = 13.sp,
                )
            }
        }
        item {
            Button(
                onClick = { vm.connect(BuildConfig.DEMO_SERVER) },
                enabled = canChange,
                modifier = Modifier.fillMaxWidth().heightIn(min = 52.dp),
                shape = RoundedCornerShape(16.dp),
            ) { Text("Reconectar API de demo") }
        }
        if (BuildConfig.DEBUG) {
            item {
                OutlinedButton(
                    onClick = vm::useSimulation,
                    enabled = canChange,
                    modifier = Modifier.fillMaxWidth(),
                ) { Text("Usar simulación sin conexión (solo debug)") }
            }
        }
        item { TextButton(onClick = close) { Text("Volver a la tienda") } }
    }
}

@Composable
internal fun UncertainScreen(saleId: String?) {
    Column(Modifier.padding(24.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        Icon(Icons.Outlined.WarningAmber, null, Modifier.size(52.dp), tint = Amber)
        Title("Cobro por revisar")
        saleId?.let { Text("Referencia conservada: $it") }
        Text(
            if (saleId == null) {
                "La solicitud pudo llegar al servidor, pero no tenemos una referencia confirmada. Bloqueamos otro intento para evitar cobrar dos veces."
            } else {
                "Conservamos esta venta, pero no pudimos recuperar su conexión. No estamos consultando el servidor; bloqueamos otro intento hasta revisarla."
            }
        )
        Text("Revisa la conexión, el servidor y PEY con el responsable. Cerrar, borrar datos o reinstalar la app no resuelve el cobro.")
    }
}

@Composable
internal fun ConnectingScreen(s: ShopState, vm: ShopViewModel, openSettings: () -> Unit) {
    Column(Modifier.padding(24.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        Title("Conectando con tu tienda…")
        MutedText(if (s.simulated) "Preparando el modo simulación." else "Consultando ${s.server}.")
        OutlinedButton(onClick = vm::refresh, enabled = !s.busy) { Text("Reintentar") }
        TextButton(onClick = openSettings) { Text("Revisar conexión") }
    }
}
