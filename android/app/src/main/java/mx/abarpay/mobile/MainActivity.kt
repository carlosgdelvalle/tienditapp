package mx.abarpay.mobile

import android.graphics.BitmapFactory
import android.os.Bundle
import android.util.Base64
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material.icons.automirrored.outlined.ReceiptLong
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.repeatOnLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.google.mlkit.vision.codescanner.GmsBarcodeScanning
import kotlinx.coroutines.delay
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

private val Purple = Color(0xFF2A0065)
private val Violet = Color(0xFF8400FF)
private val Lavender = Color(0xFFF5F0FB)
private val Green = Color(0xFF297A00)

class MainActivity: ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            MaterialTheme(colorScheme = lightColorScheme(primary = Violet, onPrimary = Color.White,
                background = Lavender, surface = Color.White, onSurface = Purple,
                secondaryContainer = Color(0xFFEADFFF))) {
                val model: ShopViewModel = viewModel()
                val state by model.ui.collectAsStateWithLifecycle()
                AbarpayApp(state, model) {
                    GmsBarcodeScanning.getClient(this).startScan()
                        .addOnSuccessListener { barcode -> barcode.rawValue?.let(model::lookup) }
                        .addOnFailureListener { model.message("No se pudo abrir el escáner. Usa el código escrito; la cámara requiere servicios de Google compatibles.") }
                }
            }
        }
    }
}

@Composable private fun AbarpayApp(s: ShopState, vm: ShopViewModel, scan: () -> Unit) {
    var settings by rememberSaveable { mutableStateOf(false) }
    var confirm by remember { mutableStateOf(false) }
    val lifecycle = LocalLifecycleOwner.current
    LaunchedEffect(s.sale?.id, lifecycle) {
        lifecycle.lifecycle.repeatOnLifecycle(Lifecycle.State.STARTED) {
            while (true) { vm.poll(); delay(3_000) }
        }
    }
    BackHandler(enabled = settings || s.sale != null || s.uncertain || s.tab != "Inicio") {
        if (settings) settings = false
        else if (s.sale != null || s.uncertain) vm.message("Conservamos el cobro. Consultar o salir de la app no confirma ni cancela el pago.")
        else vm.tab("Inicio")
    }
    val canConfirm = s.employee != null && s.cart.isNotEmpty() && s.sale == null && !s.uncertain && !s.busy
    LaunchedEffect(canConfirm) { if (!canConfirm) confirm = false }
    if (confirm && canConfirm) AlertDialog(onDismissRequest = { confirm = false }, title = { Text(if (s.simulated) "Crear cobro simulado" else "Crear QR de cobro real") },
        text = { Text(if (s.simulated) "No mueve dinero ni consulta PEY." else
            "El servidor generará un QR real. ${if (s.bootstrap?.demoCharge == true) "Modo demo: se cobra $0.01 MXN." else "El servidor calculará el importe con su catálogo."} Solo una persona autoriza el pago en su banco.") },
        confirmButton = { TextButton(onClick = { confirm = false; vm.createSale() }) { Text("Crear QR") } },
        dismissButton = { TextButton(onClick = { confirm = false }) { Text("Volver") } })
    Scaffold(containerColor = Purple, topBar = {
        Column(Modifier.statusBarsPadding().padding(horizontal = 16.dp, vertical = 12.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                if (settings) IconButton(onClick = { settings = false }) { Icon(Icons.AutoMirrored.Outlined.ArrowBack, "Volver", tint = Color.White) }
                Image(painterResource(R.drawable.abarpay_logo), "Abarpay", Modifier.width(162.dp).height(55.dp))
                Spacer(Modifier.weight(1f))
                IconButton(onClick = { settings = true }, enabled = !s.busy) { Icon(Icons.Outlined.Settings, "Conexión y alcance", tint = Color.White) }
            }
            Text(s.bootstrap?.store ?: "Tu tiendita, en tu teléfono", color = Color.White.copy(alpha = .8f), fontSize = 13.sp)
        }
    }, bottomBar = {
        if (!settings && s.employee != null && s.sale == null && !s.uncertain) NavigationBar(containerColor = Color.White) {
            listOf("Inicio" to Icons.Outlined.Home, "Cobrar" to Icons.Outlined.QrCodeScanner,
                "Inventario" to Icons.Outlined.Inventory2, "Reportes" to Icons.Outlined.BarChart).forEach { (label, icon) ->
                NavigationBarItem(selected = s.tab == label, onClick = { vm.tab(label) }, enabled = !s.busy,
                    icon = { Icon(icon, null) }, label = { Text(label, maxLines = 1, fontSize = 11.sp) })
            }
        }
    }) { padding ->
        Surface(Modifier.padding(padding).fillMaxSize(), color = Lavender, shape = RoundedCornerShape(topStart = 30.dp, topEnd = 30.dp)) {
            Column(Modifier.fillMaxSize().imePadding()) {
                if (s.busy) LinearProgressIndicator(Modifier.fillMaxWidth())
                Notice(if (s.simulated) "SIMULADO · Sin dinero real" else "DESARROLLO · API sin autenticación", !s.simulated)
                s.message?.let { Notice(it, true) }
                when {
                    settings -> Settings(s, vm) { settings = false }
                    (s.uncertain && s.sale == null) || (!s.simulated && s.server.isBlank()) -> Uncertain(s.sale?.id)
                    s.sale != null -> Payment(s, vm)
                    s.bootstrap == null -> Column(Modifier.padding(24.dp)) {
                        Text("Conectando con tu tienda…")
                        OutlinedButton(onClick = vm::refresh, enabled = !s.busy) { Text("Reintentar") }
                        TextButton(onClick = { settings = true }) { Text("Revisar conexión") }
                    }
                    s.employee == null && s.simulated -> AccessMockups(s, vm::select)
                    s.employee == null -> People(s, vm)
                    s.tab == "Inicio" -> Home(s, vm)
                    s.tab == "Cobrar" -> Checkout(s, vm, scan) { confirm = true }
                    s.tab == "Inventario" -> Inventory(s, vm)
                    else -> Reports(s, vm)
                }
            }
        }
    }
}
@Composable private fun Notice(text: String, warning: Boolean = false) {
    Text(text, Modifier.fillMaxWidth().background(if (warning) Color(0xFFFFF0D9) else Color(0xFFEADFFF)).padding(horizontal = 20.dp, vertical = 9.dp),
        color = Purple, fontSize = 12.sp, lineHeight = 17.sp)
}
@Composable private fun Title(text: String) { Text(text, style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold) }
@Composable private fun Panel(content: @Composable ColumnScope.() -> Unit) {
    Card(Modifier.fillMaxWidth(), shape = RoundedCornerShape(22.dp), colors = CardDefaults.cardColors(containerColor = Color.White),
        elevation = CardDefaults.cardElevation(defaultElevation = 1.dp)) { Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp), content = content) }
}
@Composable private fun Action(title: String, icon: ImageVector, primary: Boolean = false, onClick: () -> Unit) {
    Card(onClick = onClick, modifier = Modifier.fillMaxWidth(), shape = RoundedCornerShape(24.dp),
        colors = CardDefaults.cardColors(containerColor = if (primary) Violet else Color.White, contentColor = if (primary) Color.White else Purple)) {
        Row(Modifier.padding(24.dp).heightIn(min = if (primary) 86.dp else 40.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(icon, null, Modifier.size(if (primary) 48.dp else 36.dp))
            Text(title, Modifier.weight(1f).padding(horizontal = 20.dp), fontSize = if (primary) 30.sp else 23.sp, fontWeight = FontWeight.Bold)
            Icon(Icons.Outlined.ChevronRight, null)
        }
    }
}
@Composable private fun People(s: ShopState, vm: ShopViewModel) {
    LazyColumn(contentPadding = PaddingValues(20.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        item { Title("¿Quién cobra hoy?") }
        item { Text("Perfiles de demostración. Elegir una persona todavía no es iniciar sesión.", color = Color(0xFF666680)) }
        items(s.bootstrap!!.employees, key = { it.id }) { employee ->
            Action(employee.name + if (employee.role == "owner") " · Dueño" else " · Empleado", Icons.Outlined.Person) { vm.select(employee) }
        }
        item { Text("Próxima etapa: alta de dueño y tienda, acceso de empleados por invitación y consola web con la misma información.", fontSize = 14.sp) }
    }
}
@Composable private fun Home(s: ShopState, vm: ShopViewModel) {
    LazyColumn(contentPadding = PaddingValues(20.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        item { Text("Hola, ${s.employee?.name}", color = Color(0xFF666680)) }
        item { Action("Cobrar\ncon Pey", Icons.Outlined.QrCodeScanner, true) { vm.tab("Cobrar") } }
        item { Action("Ventas de hoy", Icons.AutoMirrored.Outlined.ReceiptLong) { vm.tab("Reportes") } }
        item { Action("Inventario", Icons.Outlined.Inventory2) { vm.tab("Inventario") } }
        item { Panel {
            Text("Ventas de hoy", fontSize = 15.sp)
            Text(s.report?.let { money(it.totalCents) } ?: "Sin datos", fontSize = 34.sp, fontWeight = FontWeight.Bold)
            Text(s.report?.let { "${it.salesCount} ventas pagadas" } ?: "No se pudo cargar el reporte", color = Green)
            HorizontalDivider()
            Text("Productos en inventario")
            Text("${s.bootstrap?.products?.sumOf { it.stock } ?: 0}", fontSize = 28.sp, fontWeight = FontWeight.Bold)
        } }
        item { TextButton(onClick = vm::refresh, enabled = !s.busy) { Text("Actualizar información") } }
    }
}
@Composable private fun Checkout(s: ShopState, vm: ShopViewModel, scan: () -> Unit, create: () -> Unit) {
    var text by rememberSaveable { mutableStateOf("") }
    var code by rememberSaveable { mutableStateOf("") }
    val products = s.bootstrap!!.products
    LazyColumn(contentPadding = PaddingValues(20.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        item { Title("Cobrar con Pey") }
        item { OutlinedTextField(text, { text = it }, Modifier.fillMaxWidth(), label = { Text("Escribe la venta") },
            placeholder = { Text("Ej. dos refrescos y unas papas") }, enabled = !s.busy, shape = RoundedCornerShape(16.dp)) }
        item { OutlinedButton(onClick = { vm.parse(text) }, enabled = text.isNotBlank() && !s.busy, modifier = Modifier.fillMaxWidth()) { Text("Agregar desde texto") } }
        item { OutlinedButton(onClick = scan, enabled = !s.busy, modifier = Modifier.fillMaxWidth().heightIn(min = 52.dp)) {
            Icon(Icons.Outlined.QrCodeScanner, null); Spacer(Modifier.width(10.dp)); Text("Escanear código")
        } }
        item { Row(verticalAlignment = Alignment.CenterVertically) {
            OutlinedTextField(code, { code = it }, Modifier.weight(1f), label = { Text("O escribe el código") }, enabled = !s.busy, singleLine = true)
            TextButton(onClick = { vm.lookup(code) }, enabled = code.isNotBlank() && !s.busy) { Text("Buscar") }
        } }
        item { Text("Catálogo", fontWeight = FontWeight.Bold) }
        items(products, key = { it.id }) { product ->
            val qty = s.cart.find { it.productId == product.id }?.qty ?: 0
            Panel {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) { Text(product.name, fontWeight = FontWeight.SemiBold); Text(money(product.priceCents)) }
                    IconButton(onClick = { vm.quantity(product.id, -1) }, enabled = qty > 0 && !s.busy) { Icon(Icons.Outlined.Remove, "Quitar ${product.name}") }
                    Text("$qty", fontWeight = FontWeight.Bold)
                    IconButton(onClick = { vm.quantity(product.id, 1) }, enabled = !s.busy) { Icon(Icons.Outlined.Add, "Agregar ${product.name}") }
                }
            }
        }
        item { Panel {
            Text("Total estimado del carrito")
            Text(money(cartEstimate(s.cart, products)), fontSize = 34.sp, fontWeight = FontWeight.Bold)
            if (s.bootstrap.demoCharge) Text(if (s.simulated) "Simulación de cobro: $0.01 MXN" else "Modo demo: se cobra $0.01 MXN", fontWeight = FontWeight.Bold)
            Text("El servidor valida los precios al crear el cobro.", fontSize = 12.sp)
            Button(onClick = create, enabled = s.cart.isNotEmpty() && !s.busy, modifier = Modifier.fillMaxWidth().heightIn(min = 56.dp), shape = RoundedCornerShape(16.dp)) { Text("Revisar y cobrar", fontSize = 18.sp) }
        } }
    }
}
@Composable private fun Inventory(s: ShopState, vm: ShopViewModel) {
    var query by rememberSaveable { mutableStateOf("") }
    val products = s.bootstrap!!.products.filter { it.name.contains(query, ignoreCase = true) }
    LazyColumn(contentPadding = PaddingValues(20.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        item { Title("Inventario") }
        item { OutlinedTextField(query, { query = it }, Modifier.fillMaxWidth(), placeholder = { Text("Buscar producto") },
            leadingIcon = { Icon(Icons.Outlined.Search, null) }, singleLine = true, shape = RoundedCornerShape(28.dp)) }
        if (products.isEmpty()) item { Text("No encontramos productos con ese nombre.") }
        items(products, key = { it.id }) { p -> Panel {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Outlined.Inventory2, null, Modifier.size(32.dp), tint = Violet)
                Column(Modifier.weight(1f).padding(horizontal = 16.dp)) { Text(p.name, fontWeight = FontWeight.Bold); Text(money(p.priceCents)) }
                Text("${p.stock}", color = if (p.stock <= 5) Color(0xFF9A5600) else Purple, fontSize = 24.sp, fontWeight = FontWeight.Bold)
            }
        } }
        item { Text("Consulta de existencias. El conteo y ajuste de inventario requieren nuevos endpoints con permisos del dueño.", fontSize = 13.sp) }
        item { TextButton(onClick = vm::refresh, enabled = !s.busy) { Text("Actualizar inventario") } }
    }
}
@Composable private fun Reports(s: ShopState, vm: ShopViewModel) {
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
        item { Text("Día de la tienda: Ciudad de México", fontSize = 13.sp) }
        item { Panel {
            Text("Ventas totales")
            Text(money(r?.totalCents ?: 0), fontSize = 36.sp, fontWeight = FontWeight.Bold)
            Text("Cobrado por CoDi: ${money(r?.chargedCents ?: 0)}")
            HorizontalDivider()
            Text("Número de ventas: ${r?.salesCount ?: 0}")
            Text("Ticket promedio: ${money(if ((r?.salesCount ?: 0) > 0) r!!.totalCents / r.salesCount else 0)}")
        } }
        if ((r?.pending ?: 0) > 0) item { Notice("${r!!.pending} cobro(s) por conciliar. Revisa antes de cerrar caja.", true) }
        item { Panel {
            Text("Por persona", fontWeight = FontWeight.Bold)
            if (r?.employees.isNullOrEmpty()) Text("Aún no hay ventas pagadas.")
            r?.employees?.forEach { Text("${it.first} · ${money(it.second)}") }
        } }
        item { Panel {
            Text("Productos más vendidos", fontWeight = FontWeight.Bold)
            if (r?.top.isNullOrEmpty()) Text("Los verás después de confirmar ventas.")
            r?.top?.forEach { Text("${it.first} · ${it.second}") }
        } }
        item { TextButton(onClick = vm::refresh, enabled = !s.busy) { Text("Actualizar reporte") } }
    }
}
@Composable private fun Payment(s: ShopState, vm: ShopViewModel) {
    val sale = s.sale!!
    var now by remember { mutableDoubleStateOf(System.currentTimeMillis() / 1000.0) }
    LaunchedEffect(sale.id, sale.paid) {
        while (!sale.paid) { now = System.currentTimeMillis() / 1000.0; delay(1_000) }
    }
    val bitmap by produceState<ImageBitmap?>(null, sale.qrImage) {
        value = withContext(Dispatchers.Default) {
            runCatching {
                require(sale.qrImage.length <= 3_000_000)
                require(sale.qrImage.startsWith("data:image/png;base64,") || sale.qrImage.startsWith("data:image/jpeg;base64,"))
                val raw = Base64.decode(sale.qrImage.substringAfter(','), Base64.DEFAULT)
                val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
                BitmapFactory.decodeByteArray(raw, 0, raw.size, bounds)
                require(bounds.outWidth in 1..4096 && bounds.outHeight in 1..4096)
                val options = BitmapFactory.Options().apply { inSampleSize = 1 }
                while (maxOf(bounds.outWidth, bounds.outHeight) / options.inSampleSize > 1024) options.inSampleSize *= 2
                BitmapFactory.decodeByteArray(raw, 0, raw.size, options)?.asImageBitmap()
            }.getOrNull()
        }
    }
    val bitmapSnapshot = bitmap
    LazyColumn(contentPadding = PaddingValues(20.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        item { Title(if (sale.paid) "¡Cobro exitoso!" else "Cobrar con Pey") }
        item { Panel {
            if (sale.paid) Icon(Icons.Outlined.CheckCircle, null, Modifier.size(96.dp).align(Alignment.CenterHorizontally), tint = Green)
            else if (s.simulated) {
                Icon(Icons.Outlined.QrCode2, null, Modifier.size(112.dp).align(Alignment.CenterHorizontally), tint = Violet)
                Text("SIMULADO · Este símbolo no sirve para pagar", textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth())
            } else if (canDisplayQr(sale, now, s.qrHidden) && bitmapSnapshot != null) {
                Image(bitmapSnapshot, "QR CoDi de esta venta", Modifier.fillMaxWidth().aspectRatio(1f).padding(10.dp))
            } else Text(if (s.qrHidden) "QR oculto" else "QR no disponible o vencido. Conserva esta venta; no generes otro cobro.")
            Text(if (sale.paid) "Monto recibido" else "Monto a cobrar", Modifier.fillMaxWidth(), textAlign = TextAlign.Center)
            Text(money(sale.chargedCents), Modifier.fillMaxWidth(), fontSize = 42.sp, fontWeight = FontWeight.Bold, textAlign = TextAlign.Center)
            if (sale.chargedCents != sale.totalCents) {
                Text("Modo demo: se cobra ${money(sale.chargedCents)} MXN", fontWeight = FontWeight.Bold)
                Text("Total de productos: ${money(sale.totalCents)}")
            }
            Text(when {
                sale.paid && s.simulated -> "Confirmación SIMULADA. No hubo pago."
                sale.paid -> "Pago confirmado por el servidor con PEY."
                sale.status == "expired" -> "Cobro vencido o cancelado localmente. Un pago tardío todavía puede llegar."
                sale.status == "por_conciliar" -> "Por conciliar. No vuelvas a cobrar hasta revisar."
                else -> "Esperando confirmación del servidor…"
            })
            Text("Venta: ${sale.id}", fontSize = 12.sp)
            sale.txId?.let { Text("Folio PEY: $it", fontSize = 12.sp) }
            sale.note?.let { Text(it, fontSize = 13.sp) }
        } }
        if (sale.paid) item { Button(onClick = vm::newSale, modifier = Modifier.fillMaxWidth().heightIn(min = 56.dp)) { Text("Nuevo cobro") } }
        else {
            item { OutlinedButton(onClick = vm::checkNow, enabled = !s.busy, modifier = Modifier.fillMaxWidth()) { Text("Consultar estado") } }
            if (s.simulated) item { Button(onClick = vm::simulatePayment, modifier = Modifier.fillMaxWidth()) { Text("Simular confirmación · sin dinero") } }
            else if (!s.qrHidden) item { TextButton(onClick = vm::hideQr, enabled = !s.busy, modifier = Modifier.fillMaxWidth()) { Text("Dejar de mostrar QR") } }
            item { Text("El QR y una captura del cliente no prueban el pago. Solo el servidor puede confirmarlo.", fontSize = 13.sp) }
        }
    }
}
@Composable private fun Uncertain(saleId: String? = null) {
    Column(Modifier.padding(24.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        Icon(Icons.Outlined.WarningAmber, null, Modifier.size(52.dp), tint = Color(0xFF9A5600))
        Title("Cobro por revisar")
        saleId?.let { Text("Referencia conservada: $it") }
        Text(if (saleId == null) "La solicitud pudo llegar al servidor, pero no tenemos una referencia confirmada. Bloqueamos otro intento para evitar cobrar dos veces."
            else "Conservamos esta venta, pero no pudimos recuperar su conexión. No estamos consultando el servidor; bloqueamos otro intento hasta revisarla.")
        Text("Revisa la conexión, el servidor y PEY con el responsable. Cerrar, borrar datos o reinstalar la app no resuelve el cobro.")
    }
}
@Composable private fun Settings(s: ShopState, vm: ShopViewModel, close: () -> Unit) {
    var url by rememberSaveable { mutableStateOf(s.server.ifBlank { "http://10.0.2.2:8000" }) }
    var accepted by rememberSaveable { mutableStateOf(false) }
    val canChange = s.sale == null && !s.uncertain && !s.busy
    LazyColumn(contentPadding = PaddingValues(20.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        item { Title("Conexión de desarrollo") }
        item { Text("SQLite permanece en el servidor. El móvil y la consola web usarán la misma API. No hay claves de PEY ni OpenAI en esta app.") }
        item { Panel {
            Text("Pendiente: cuentas y tiendas", fontWeight = FontWeight.Bold)
            Text("El backend actual es de una sola tienda y no autentica. Alta del dueño, invitaciones de empleados, permisos y separación entre tiendas todavía no están implementados.")
            Text("Login y registro son mockups con datos ficticios. Google y Apple también son simulados: no conectan cuentas ni piden credenciales.")
        } }
        if (s.simulated && s.employee != null) item {
            OutlinedButton(onClick = { vm.leaveMockProfile(); close() }, enabled = canChange && s.cart.isEmpty(), modifier = Modifier.fillMaxWidth()) { Text("Volver al login simulado") }
            if (s.cart.isNotEmpty()) Text("Termina o vacía el carrito antes de cambiar de perfil.", fontSize = 12.sp)
        }
        item { OutlinedTextField(url, { url = it; accepted = false }, Modifier.fillMaxWidth(), label = { Text("Dirección del servidor") }, singleLine = true, enabled = canChange) }
        item { Row(verticalAlignment = Alignment.CenterVertically) {
            Checkbox(accepted, { accepted = it }, enabled = canChange)
            Text("Es mi servidor de desarrollo; entiendo que los cobros PEY son reales y no hay control de acceso.", fontSize = 13.sp)
        } }
        item { Button(onClick = { vm.connect(url) }, enabled = canChange && accepted, modifier = Modifier.fillMaxWidth()) { Text("Conectar API de desarrollo") } }
        item { OutlinedButton(onClick = vm::useSimulation, enabled = canChange, modifier = Modifier.fillMaxWidth()) { Text("Usar simulación sin conexión") } }
        item { TextButton(onClick = close) { Text("Volver a la tienda") } }
    }
}
