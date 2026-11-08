package mx.abarpay.mobile

import android.app.Activity
import android.content.ActivityNotFoundException
import android.content.Intent
import android.speech.RecognizerIntent
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

@Composable
internal fun CheckoutScreen(s: ShopState, vm: ShopViewModel, scan: () -> Unit) {
    var text by rememberSaveable { mutableStateOf("") }
    var code by rememberSaveable { mutableStateOf("") }
    var search by rememberSaveable { mutableStateOf("") }
    var quickOnly by rememberSaveable { mutableStateOf(false) }
    var textOpen by rememberSaveable { mutableStateOf(false) }
    var cashInput by rememberSaveable { mutableStateOf("") }
    var customerOpen by rememberSaveable { mutableStateOf(false) }
    var quantityProductId by rememberSaveable { mutableStateOf<Int?>(null) }
    val listState = rememberLazyListState()
    val scope = rememberCoroutineScope()

    val voice = rememberLauncherForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
        val spoken = result.data?.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS)?.firstOrNull()
        if (result.resultCode == Activity.RESULT_OK && !spoken.isNullOrBlank()) {
            text = spoken
            vm.parse(spoken)
        }
    }
    fun dictate() {
        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, "es-MX")
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_PREFERENCE, "es-MX")
            putExtra(RecognizerIntent.EXTRA_PROMPT, "Dicta la venta: dos cocas y medio kilo de tortillas")
        }
        try {
            voice.launch(intent)
        } catch (_: ActivityNotFoundException) {
            vm.message("Este teléfono no tiene reconocimiento de voz. Escribe la venta.")
        }
    }

    LaunchedEffect(s.cart.isEmpty()) {
        if (s.cart.isEmpty()) cashInput = ""
    }

    val products = s.bootstrap?.products.orEmpty()
    val visible = products.filter {
        (search.isBlank() || it.name.contains(search, ignoreCase = true)) && (!quickOnly || it.quick)
    }
    val total = runCatching { cartEstimate(s.cart, products) }.getOrDefault(0)
    val canPay = s.cart.isNotEmpty() && !s.busy && s.sale == null &&
        (s.paymentMethod != PAYMENT_FIADO || s.customer != null)

    if (customerOpen) {
        AddCustomerDialog(
            onDismiss = { customerOpen = false },
            onConfirm = { name, phone ->
                customerOpen = false
                vm.addCustomer(name, phone)
            },
        )
    }
    s.linkCode?.let { linkCode ->
        LinkDialog(
            code = linkCode,
            products = products,
            onDismiss = vm::cancelLink,
            onPick = { vm.link(it) },
        )
    }
    quantityProductId?.let { productId ->
        val product = products.firstOrNull { it.id == productId }
        if (product != null) {
            val current = s.cart.find { it.productId == productId }?.qtyMilli ?: 0
            QuantityDialog(
                product = product,
                currentMilli = current,
                onDismiss = { quantityProductId = null },
                onSet = { target -> vm.quantity(product.id, target - current) },
            )
        }
    }

    Column(Modifier.fillMaxSize()) {
        LazyColumn(
            state = listState,
            modifier = Modifier.weight(1f),
            contentPadding = PaddingValues(20.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
        item { Title("Cobrar") }
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Button(
                    onClick = scan,
                    enabled = !s.busy,
                    modifier = Modifier.weight(1f).heightIn(min = 64.dp),
                    shape = RoundedCornerShape(16.dp),
                ) {
                    Icon(Icons.Outlined.QrCodeScanner, null)
                    Spacer(Modifier.width(6.dp))
                    Text("Escanear código")
                }
                OutlinedButton(
                    onClick = { dictate() },
                    enabled = !s.busy,
                    modifier = Modifier.weight(1f).heightIn(min = 64.dp),
                ) {
                    Icon(Icons.Outlined.Mic, "Dictar venta")
                    Spacer(Modifier.width(6.dp))
                    Text("Dictar")
                }
            }
        }
        item { MutedText("Escanea o dicta la venta. El teclado es opcional; los precios y el total los pone el servidor.") }
        item {
            TextButton(
                onClick = { textOpen = !textOpen },
                modifier = Modifier.fillMaxWidth(),
            ) {
                Icon(Icons.Outlined.Keyboard, null, Modifier.size(18.dp))
                Spacer(Modifier.width(6.dp))
                Text(if (textOpen) "Ocultar venta por texto" else "Escribir venta o código")
            }
        }
        if (textOpen) {
            item {
                OutlinedTextField(
                    text, { text = it },
                    Modifier.fillMaxWidth(),
                    label = { Text("Escribe la venta") },
                    placeholder = { Text("Ej. dos cocas y medio kilo de tortillas") },
                    enabled = !s.busy,
                    shape = RoundedCornerShape(16.dp),
                )
            }
            item {
                Button(
                    onClick = { vm.parse(text) },
                    enabled = text.isNotBlank() && !s.busy,
                    modifier = Modifier.fillMaxWidth().heightIn(min = 50.dp),
                    shape = RoundedCornerShape(16.dp),
                ) { Text("Agregar desde texto") }
            }
            item {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    OutlinedTextField(
                        code, { code = it },
                        Modifier.weight(1f),
                        label = { Text("O escribe el código") },
                        singleLine = true,
                        enabled = !s.busy,
                    )
                    TextButton(onClick = { vm.lookup(code) }, enabled = code.isNotBlank() && !s.busy) {
                        Text("Buscar")
                    }
                }
            }
        }
        item { SectionLabel("Catálogo") }
        item {
            OutlinedTextField(
                search, { search = it },
                Modifier.fillMaxWidth(),
                placeholder = { Text("Buscar producto") },
                leadingIcon = { Icon(Icons.Outlined.Search, null) },
                singleLine = true,
                shape = RoundedCornerShape(28.dp),
            )
        }
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                FilterChip(
                    selected = quickOnly,
                    onClick = { quickOnly = !quickOnly },
                    label = { Text("Rápidos") },
                    leadingIcon = if (quickOnly) {
                        { Icon(Icons.Outlined.Check, null, Modifier.size(16.dp)) }
                    } else null,
                )
                Text("Los más vendidos de la tienda", color = Muted, fontSize = 12.sp, modifier = Modifier.align(Alignment.CenterVertically))
            }
        }
        if (visible.isEmpty()) item { Text("No encontramos productos con ese nombre.") }
        items(visible, key = { "product-${it.id}" }) { product ->
            val qty = s.cart.find { it.productId == product.id }?.qtyMilli ?: 0
            Panel {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text(product.name, fontWeight = FontWeight.SemiBold)
                        Text("${money(product.priceCents)} · ${qtyText(1000, product.unit)}", color = Muted, fontSize = 12.sp)
                        Text(
                            "Stock ${qtyText(product.stockMilli, product.unit)}" + if (product.stockMilli <= product.lowStockMilli) " · bajo" else "",
                            color = if (product.stockMilli <= product.lowStockMilli) Amber else Muted,
                            fontSize = 11.sp,
                        )
                    }
                    IconButton(
                        onClick = { vm.quantity(product.id, decrementStep(qty)) },
                        enabled = qty > 0 && !s.busy,
                    ) { Icon(Icons.Outlined.Remove, "Quitar ${product.name}") }
                    Text(
                        qtyText(qty, product.unit),
                        Modifier.widthIn(min = 44.dp).clickable { quantityProductId = product.id },
                        textAlign = TextAlign.Center,
                        fontWeight = FontWeight.Bold,
                        fontSize = 13.sp,
                    )
                    IconButton(
                        onClick = { vm.quantity(product.id, 1000) },
                        enabled = !s.busy,
                    ) { Icon(Icons.Outlined.Add, "Agregar ${product.name}") }
                }
            }
        }
        item { SectionLabel("Carrito") }
        if (s.cart.isEmpty()) {
            item { Text("El carrito está vacío. Agrega productos por texto, voz o código.") }
        }
        items(s.cart, key = { "cart-${it.productId}" }) { line ->
            val product = products.firstOrNull { it.id == line.productId } ?: return@items
            Panel {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text(product.name, fontWeight = FontWeight.SemiBold)
                        Text(
                            "${qtyText(line.qtyMilli, product.unit)} × ${money(product.priceCents)}",
                            color = Muted,
                            fontSize = 12.sp,
                        )
                    }
                    Text(
                        money(lineTotalCents(product.priceCents, line.qtyMilli)),
                        fontWeight = FontWeight.Bold,
                    )
                }
                Row(verticalAlignment = Alignment.CenterVertically) {
                    IconButton(
                        onClick = { vm.quantity(product.id, decrementStep(line.qtyMilli)) },
                        enabled = !s.busy,
                    ) { Icon(Icons.Outlined.RemoveCircleOutline, "Quitar una unidad de ${product.name}") }
                    Text(
                        qtyText(line.qtyMilli, product.unit),
                        modifier = Modifier.weight(1f).clickable { quantityProductId = product.id },
                        textAlign = TextAlign.Center,
                    )
                    IconButton(
                        onClick = { vm.quantity(product.id, 1000) },
                        enabled = !s.busy,
                    ) { Icon(Icons.Outlined.AddCircleOutline, "Agregar una unidad de ${product.name}") }
                }
            }
        }
        item {
            Panel {
                Text("Total del carrito")
                Text(money(total), fontSize = 36.sp, fontWeight = FontWeight.Bold)
                MutedText("El servidor confirma el importe con su catálogo al crear la venta.", 12)
                if (s.bootstrap?.demoMode == true) {
                    Text("Modo demo: PEY cobra $0.01 MXN", color = Amber, fontWeight = FontWeight.Bold, fontSize = 13.sp)
                }
                HorizontalDivider()
                Text("Forma de pago", fontWeight = FontWeight.Bold)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    FilterChip(
                        selected = s.paymentMethod == PAYMENT_CASH,
                        onClick = { vm.setPaymentMethod(PAYMENT_CASH) },
                        enabled = !s.busy,
                        modifier = Modifier.testTag("pago-efectivo"),
                        label = { Text("Efectivo") },
                        leadingIcon = { Icon(Icons.Outlined.Payments, null, Modifier.size(16.dp)) },
                    )
                    FilterChip(
                        selected = s.paymentMethod == PAYMENT_PEY,
                        onClick = { vm.setPaymentMethod(PAYMENT_PEY) },
                        enabled = !s.busy,
                        modifier = Modifier.testTag("pago-pey"),
                        label = { Text("PEY / CoDi") },
                        leadingIcon = { Icon(Icons.Outlined.QrCode2, null, Modifier.size(16.dp)) },
                    )
                    FilterChip(
                        selected = s.paymentMethod == PAYMENT_FIADO,
                        onClick = { vm.setPaymentMethod(PAYMENT_FIADO) },
                        enabled = !s.busy,
                        modifier = Modifier.testTag("pago-fiado"),
                        label = { Text("Fiado") },
                        leadingIcon = { Icon(Icons.Outlined.AccountBalanceWallet, null, Modifier.size(16.dp)) },
                    )
                }
                MutedText(
                    when (s.paymentMethod) {
                        PAYMENT_CASH -> "Recibe el efectivo, registra el cobro y muestra el cambio. No llama a PEY."
                        PAYMENT_PEY -> "Genera un QR CoDi. Solo el servidor puede confirmarlo como paid_pey."
                        else -> "Queda a crédito del cliente. El saldo se consulta en Fiado."
                    },
                    12,
                )
                if (s.paymentMethod == PAYMENT_CASH) {
                    OutlinedTextField(
                        cashInput, { cashInput = it },
                        Modifier.fillMaxWidth().testTag("efectivo-recibido"),
                        label = { Text("Efectivo recibido (MXN)") },
                        placeholder = { Text("Ej. 100.00") },
                        singleLine = true,
                        enabled = !s.busy,
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                    )
                    val quickBills = remember(total) {
                        listOf(total, 2000, 5000, 10000, 20000)
                            .filter { it >= total && it > 0 }
                            .distinct()
                    }
                    Row(
                        Modifier.horizontalScroll(rememberScrollState()),
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Text("Recibido:", color = Muted, fontSize = 12.sp)
                        quickBills.forEach { cents ->
                            OutlinedButton(
                                onClick = {
                                    cashInput = "${cents / 100}.${(cents % 100).toString().padStart(2, '0')}"
                                },
                                enabled = !s.busy,
                                contentPadding = PaddingValues(horizontal = 14.dp, vertical = 8.dp),
                            ) { Text(money(cents)) }
                        }
                    }
                    val received = parseCashCents(cashInput)
                    if (received != null) {
                        val diff = received - total
                        Text(
                            if (diff >= 0) "Cambio: ${money(diff)}" else "Faltan ${money(-diff)}",
                            color = if (diff >= 0) Green else Amber,
                            fontWeight = FontWeight.Bold,
                        )
                    } else if (cashInput.isNotBlank()) {
                        Text("Escribe un monto válido, por ejemplo 100.00", color = Amber, fontSize = 12.sp)
                    }
                }
                if (s.paymentMethod == PAYMENT_FIADO) {
                    Text("Cliente del fiado", fontWeight = FontWeight.SemiBold)
                    Row(
                        Modifier.horizontalScroll(rememberScrollState()),
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        s.customers.forEach { customer ->
                            FilterChip(
                                selected = s.customer?.id == customer.id,
                                onClick = { vm.selectCustomer(customer) },
                                enabled = !s.busy,
                                label = { Text("${customer.name} · ${money(customer.balanceCents)}") },
                            )
                        }
                        AssistChip(
                            onClick = { customerOpen = true },
                            enabled = !s.busy,
                            label = { Text("Nuevo cliente") },
                            leadingIcon = { Icon(Icons.Outlined.PersonAdd, null, Modifier.size(16.dp)) },
                        )
                    }
                    if (s.customer == null) {
                        Text("Elige un cliente para continuar.", color = Amber, fontSize = 12.sp)
                    }
                }
                val cashCents = parseCashCents(cashInput)
                Button(
                    onClick = {
                        when (s.paymentMethod) {
                            PAYMENT_CASH -> cashCents?.let { vm.payCash(it) }
                            PAYMENT_PEY -> vm.payPey()
                            else -> vm.payFiado()
                        }
                    },
                    enabled = canPay && (s.paymentMethod != PAYMENT_CASH || (cashCents != null && cashCents >= total)),
                    modifier = Modifier.fillMaxWidth().heightIn(min = 56.dp),
                    shape = RoundedCornerShape(16.dp),
                ) {
                    Text(
                        when (s.paymentMethod) {
                            PAYMENT_CASH -> "Cobrar en efectivo"
                            PAYMENT_PEY -> "Generar QR PEY"
                            else -> "Cobrar a fiado"
                        },
                        fontSize = 17.sp,
                    )
                }
            }
        }
        }
        CartActionBar(
            count = s.cart.size,
            total = total,
            onCobrar = {
                if (s.cart.isNotEmpty()) {
                    scope.launch {
                        val last = (listState.layoutInfo.totalItemsCount - 1).coerceAtLeast(0)
                        listState.animateScrollToItem(last)
                    }
                }
            },
        )
    }
}

@Composable
private fun CartActionBar(count: Int, total: Long, onCobrar: () -> Unit) {
    Surface(tonalElevation = 6.dp) {
        Row(
            Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 10.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Column(Modifier.weight(1f)) {
                Text(if (count == 1) "1 producto" else "$count productos", color = Muted, fontSize = 12.sp)
                Text(money(total), fontWeight = FontWeight.Bold, fontSize = 24.sp)
            }
            Button(
                onClick = onCobrar,
                enabled = count > 0,
                modifier = Modifier.heightIn(min = 52.dp),
                shape = RoundedCornerShape(16.dp),
            ) { Text("Cobrar") }
        }
    }
}

@Composable
private fun QuantityDialog(
    product: Product,
    currentMilli: Int,
    onDismiss: () -> Unit,
    onSet: (Int) -> Unit,
) {
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(product.name) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Text("Cantidad actual: ${qtyText(currentMilli, product.unit)}", fontWeight = FontWeight.SemiBold)
                if (product.unit == "kg") {
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        listOf(250, 500, 1000, 2000).forEach { target ->
                            OutlinedButton(onClick = { onSet(target) }, enabled = target != currentMilli) {
                                Text(qtyText(target, product.unit))
                            }
                        }
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        OutlinedButton(onClick = { onSet(currentMilli - 100) }, enabled = currentMilli >= 100) {
                            Text("−100 g")
                        }
                        OutlinedButton(onClick = { onSet(currentMilli + 100) }) {
                            Text("+100 g")
                        }
                    }
                } else {
                    Row(horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                        OutlinedButton(onClick = { onSet(currentMilli - 1000) }, enabled = currentMilli > 0) {
                            Text("−1 pza")
                        }
                        OutlinedButton(onClick = { onSet(currentMilli + 1000) }) {
                            Text("+1 pza")
                        }
                    }
                }
            }
        },
        confirmButton = { TextButton(onClick = onDismiss) { Text("Listo") } },
    )
}

@Composable
internal fun AddCustomerDialog(onDismiss: () -> Unit, onConfirm: (String, String) -> Unit) {
    var name by rememberSaveable { mutableStateOf("") }
    var phone by rememberSaveable { mutableStateOf("") }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Nuevo cliente de fiado") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text("Se guarda en el servidor. No pidas datos sensibles.", fontSize = 12.sp, color = Muted)
                OutlinedTextField(name, { name = it }, singleLine = true, label = { Text("Nombre") })
                OutlinedTextField(
                    phone, { phone = it },
                    singleLine = true,
                    label = { Text("Teléfono (opcional)") },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Phone),
                )
            }
        },
        confirmButton = {
            TextButton(onClick = { onConfirm(name, phone) }, enabled = name.isNotBlank()) {
                Text("Agregar cliente")
            }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancelar") } },
    )
}

@Composable
private fun LinkDialog(code: String, products: List<Product>, onDismiss: () -> Unit, onPick: (Int) -> Unit) {
    var query by rememberSaveable { mutableStateOf("") }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Código sin enlazar") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("El código $code no está en el catálogo. Elige el producto para enlazarlo.")
                OutlinedTextField(query, { query = it }, singleLine = true, label = { Text("Buscar producto") })
                LazyColumn(Modifier.heightIn(max = 280.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                    items(products.filter { it.name.contains(query, ignoreCase = true) }, key = { it.id }) { product ->
                        TextButton(onClick = { onPick(product.id) }, modifier = Modifier.fillMaxWidth()) {
                            Text(product.name)
                        }
                    }
                }
            }
        },
        confirmButton = { TextButton(onClick = onDismiss) { Text("Cancelar") } },
    )
}

@Composable
internal fun SaleScreen(s: ShopState, vm: ShopViewModel) {
    val sale = s.sale ?: return
    val settled = sale.settled
    var now by remember { mutableDoubleStateOf(System.currentTimeMillis() / 1000.0) }
    LaunchedEffect(sale.id, settled) {
        while (!settled) {
            now = System.currentTimeMillis() / 1000.0
            delay(1_000)
        }
    }
    val qr = rememberQrBitmap(sale.qrImage)

    LazyColumn(contentPadding = PaddingValues(20.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        item { Title(saleHeadline(sale)) }
        item {
            Panel {
                if (settled) {
                    Icon(
                        Icons.Outlined.CheckCircle, null,
                        Modifier.size(84.dp).align(Alignment.CenterHorizontally),
                        tint = Green,
                    )
                }
                val displayCents = if (sale.paymentMethod == PAYMENT_PEY) sale.chargedCents else sale.totalCents
                Text(
                    when {
                        settled && sale.paymentMethod == PAYMENT_PEY -> "Monto recibido"
                        settled -> "Total cobrado"
                        sale.paymentMethod == PAYMENT_PEY -> "Monto a cobrar"
                        else -> "Total de la venta"
                    },
                    Modifier.fillMaxWidth(),
                    textAlign = TextAlign.Center,
                )
                Text(
                    money(displayCents),
                    Modifier.fillMaxWidth(),
                    fontSize = 40.sp,
                    fontWeight = FontWeight.Bold,
                    textAlign = TextAlign.Center,
                )
                HorizontalDivider()
                InfoRow("Forma de pago", methodLabel(sale.paymentMethod))
                InfoRow("Estado", statusLabel(sale.status))
                if (sale.paymentMethod == PAYMENT_PEY && sale.chargedCents != sale.totalCents) {
                    Text(
                        "Modo demo: se cobra ${money(sale.chargedCents)} MXN",
                        fontWeight = FontWeight.Bold,
                        color = Amber,
                        fontSize = 13.sp,
                    )
                    Text("Total de productos: ${money(sale.totalCents)}", fontSize = 12.sp, color = Muted)
                }
                Text("Venta: ${sale.id}", fontSize = 11.sp, color = Muted)
                sale.qrId?.let { Text("QR PEY: $it", fontSize = 11.sp, color = Muted) }
                sale.txId?.let { Text("Folio PEY: $it", fontSize = 11.sp, color = Muted) }
                sale.note?.let { Text(it, fontSize = 13.sp) }
            }
        }
        if (sale.paymentMethod == PAYMENT_CASH) {
            item {
                Panel {
                    Text("Efectivo", fontWeight = FontWeight.Bold)
                    val received = sale.cashReceivedCents ?: sale.totalCents
                    val change = sale.changeCents ?: (received - sale.totalCents)
                    InfoRow("Recibido", money(received))
                    Text(
                        "Cambio: ${money(change)}",
                        fontSize = 26.sp,
                        fontWeight = FontWeight.Bold,
                        color = Green,
                    )
                    MutedText("Cobro final registrado por el servidor. No se consultó PEY.", 12)
                }
            }
        }
        if (sale.paymentMethod == PAYMENT_FIADO) {
            item {
                Panel {
                    Text("Crédito del cliente", fontWeight = FontWeight.Bold)
                    InfoRow("Cliente", sale.customerName ?: "Cliente #${sale.customerId ?: 0}")
                    InfoRow(
                        "Saldo después de la venta",
                        sale.customerBalanceCents?.let { money(it) } ?: "Consultando en el servidor…",
                        strong = true,
                    )
                    MutedText("La venta quedó a crédito. Registra abonos desde la pestaña Fiado.", 12)
                }
            }
        }
        if (sale.paymentMethod == PAYMENT_PEY) {
            if (!settled) {
                item {
                    Panel {
                        if (s.simulated) {
                            Icon(
                                Icons.Outlined.QrCode2, null,
                                Modifier.size(112.dp).align(Alignment.CenterHorizontally),
                                tint = Violet,
                            )
                            Text(
                                "SIMULADO · Este símbolo no sirve para pagar",
                                Modifier.fillMaxWidth(),
                                textAlign = TextAlign.Center,
                            )
                        } else if (canDisplayQr(sale, now, s.qrHidden) && qr != null) {
                            Image(qr, "QR CoDi de esta venta", Modifier.fillMaxWidth().aspectRatio(1f).padding(10.dp))
                        } else {
                            Text(
                                if (s.qrHidden) "QR oculto en este teléfono."
                                else "QR no disponible o vencido. Conserva esta venta; no generes otro cobro.",
                            )
                        }
                        Text("Monto a cobrar", Modifier.fillMaxWidth(), textAlign = TextAlign.Center)
                        Text(
                            money(sale.chargedCents),
                            Modifier.fillMaxWidth(),
                            fontSize = 40.sp,
                            fontWeight = FontWeight.Bold,
                            textAlign = TextAlign.Center,
                        )
                    }
                }
            }
            item {
                Text(
                    when (sale.status) {
                        "paid_pey" -> "Pago confirmado por el servidor con PEY."
                        "por_conciliar" -> "El pago está por conciliar. Consultaremos de nuevo; no vuelvas a cobrar."
                        "failed" -> "PEY rechazó el cobro. No se generó un pago."
                        "canceled" -> "La venta fue cancelada."
                        "expired" -> "Cobro vencido. Un pago tardío todavía puede llegar; conservamos la referencia."
                        else -> "Esperando confirmación del servidor…"
                    },
                    color = Muted,
                    fontSize = 13.sp,
                )
            }
        }
        item {
            if (settled) {
                Button(
                    onClick = vm::newSale,
                    enabled = !s.busy,
                    modifier = Modifier.fillMaxWidth().heightIn(min = 56.dp),
                    shape = RoundedCornerShape(16.dp),
                ) { Text("Nuevo cobro") }
            } else if (sale.failed || sale.status == "canceled" || sale.status == "expired") {
                Button(
                    onClick = vm::dismissSale,
                    enabled = !s.busy,
                    modifier = Modifier.fillMaxWidth().heightIn(min = 56.dp),
                    shape = RoundedCornerShape(16.dp),
                ) { Text(if (sale.status == "expired") "Nuevo cobro" else "Volver al carrito") }
            } else {
                Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    OutlinedButton(
                        onClick = vm::checkNow,
                        enabled = !s.busy,
                        modifier = Modifier.fillMaxWidth().heightIn(min = 52.dp),
                    ) { Text("Consultar estado") }
                    if (s.simulated) {
                        Button(onClick = vm::simulatePayment, modifier = Modifier.fillMaxWidth()) {
                            Text("Simular confirmación · sin dinero")
                        }
                    } else if (!s.qrHidden) {
                        TextButton(onClick = vm::hideQr, enabled = !s.busy, modifier = Modifier.fillMaxWidth()) {
                            Text("Dejar de mostrar QR")
                        }
                    }
                    MutedText("El QR y una captura del cliente no prueban el pago. Solo el servidor puede confirmarlo.", 12)
                }
            }
        }
    }
}

private fun saleHeadline(sale: Sale): String = when (sale.status) {
    "paid_cash" -> "Cobro en efectivo registrado"
    "paid_pey" -> "¡Pago PEY confirmado!"
    "credit" -> "Fiado registrado"
    "failed" -> "El pago no se completó"
    "canceled" -> "Venta cancelada"
    "por_conciliar" -> "Pago por conciliar"
    else -> "Cobro con PEY"
}
