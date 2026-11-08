package mx.abarpay.mobile

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.BarChart
import androidx.compose.material.icons.outlined.Home
import androidx.compose.material.icons.outlined.Inventory2
import androidx.compose.material.icons.outlined.People
import androidx.compose.material.icons.outlined.PointOfSale
import androidx.compose.material.icons.outlined.Settings
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.repeatOnLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import kotlinx.coroutines.delay

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            AbarpayTheme {
                val model: ShopViewModel = viewModel()
                val state by model.ui.collectAsStateWithLifecycle()
                var scanning by rememberSaveable { mutableStateOf(false) }
                Box(Modifier.fillMaxSize()) {
                    AbarpayApp(state, model) { scanning = true }
                    if (scanning) {
                        ContinuousScannerScreen(
                            onResult = { code ->
                                scanning = false
                                model.lookup(code)
                            },
                            onClose = { scanning = false },
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun AbarpayApp(s: ShopState, vm: ShopViewModel, scan: () -> Unit) {
    var settings by rememberSaveable { mutableStateOf(false) }
    val lifecycle = LocalLifecycleOwner.current

    LaunchedEffect(s.sale?.id, s.simulated) {
        val sale = s.sale ?: return@LaunchedEffect
        if (sale.paymentMethod != PAYMENT_PEY || sale.settled) return@LaunchedEffect
        lifecycle.lifecycle.repeatOnLifecycle(Lifecycle.State.STARTED) {
            while (true) {
                vm.poll()
                delay(3_000)
            }
        }
    }

    BackHandler(enabled = settings || s.customerDetail != null || s.sale != null || s.uncertain || s.tab != "Inicio") {
        when {
            settings -> settings = false
            s.customerDetail != null -> vm.closeCustomer()
            s.sale != null || s.uncertain ->
                vm.message("Conservamos el cobro. Consultar o salir de la app no confirma ni cancela el pago.")
            else -> vm.tab("Inicio")
        }
    }

    Scaffold(
        containerColor = Purple,
        topBar = {
            Column(Modifier.statusBarsPadding().padding(horizontal = 16.dp, vertical = 12.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Image(painterResource(R.drawable.abarpay_logo), "Abarpay", Modifier.width(162.dp).height(55.dp))
                    Spacer(Modifier.weight(1f))
                    IconButton(onClick = { settings = true }, enabled = !s.busy) {
                        Icon(Icons.Outlined.Settings, "Conexión y alcance", tint = Color.White)
                    }
                }
                Text(
                    s.bootstrap?.store?.name ?: "Tu tiendita, en tu teléfono",
                    color = Color.White.copy(alpha = .82f),
                    fontSize = 13.sp,
                )
                Text(
                    if (s.simulated) "Simulación local" else (s.server.ifBlank { "Sin servidor configurado" }),
                    color = Color.White.copy(alpha = .55f),
                    fontSize = 11.sp,
                )
            }
        },
        bottomBar = {
            if (!settings && s.employee != null && s.sale == null && !s.uncertain) {
                NavigationBar(containerColor = Color.White) {
                    listOf(
                        "Inicio" to Icons.Outlined.Home,
                        "Cobrar" to Icons.Outlined.PointOfSale,
                        "Fiado" to Icons.Outlined.People,
                        "Inventario" to Icons.Outlined.Inventory2,
                        "Reportes" to Icons.Outlined.BarChart,
                    ).forEach { (label, icon) ->
                        NavigationBarItem(
                            selected = s.tab == label,
                            onClick = { vm.tab(label) },
                            enabled = !s.busy,
                            modifier = Modifier.testTag("tab-$label"),
                            icon = { Icon(icon, label) },
                            label = { Text(label, maxLines = 1, fontSize = 10.sp) },
                        )
                    }
                }
            }
        },
    ) { padding ->
        Surface(
            Modifier.padding(padding).fillMaxSize(),
            color = Lavender,
            shape = RoundedCornerShape(topStart = 30.dp, topEnd = 30.dp),
        ) {
            Column(Modifier.fillMaxSize().imePadding()) {
                if (s.busy) LinearProgressIndicator(Modifier.fillMaxWidth())
                Notice(
                    when {
                        s.simulated -> "SIMULADO · Sin dinero real"
                        s.bootstrap?.demoMode == true -> "MODO DEMO · PEY cobra $0.01 MXN"
                        else -> "DESARROLLO · API sin autenticación"
                    },
                    warning = !s.simulated,
                )
                s.message?.let { Notice(it, true) }
                when {
                    settings -> SettingsScreen(s, vm) { settings = false }
                    !s.busy && (s.uncertain || (!s.simulated && s.server.isBlank())) -> UncertainScreen(s.sale?.id)
                    s.sale != null -> SaleScreen(s, vm)
                    s.bootstrap == null -> ConnectingScreen(s, vm) { settings = true }
                    s.employee == null && s.simulated -> AccessMockups(s, vm::select)
                    s.employee == null -> People(s, vm)
                    s.tab == "Inicio" -> HomeScreen(s, vm)
                    s.tab == "Cobrar" -> CheckoutScreen(s, vm, scan)
                    s.tab == "Fiado" -> FiadoScreen(s, vm)
                    s.tab == "Inventario" -> InventoryScreen(s, vm)
                    else -> ReportsScreen(s, vm)
                }
            }
        }
    }
}

@Composable
private fun People(s: ShopState, vm: ShopViewModel) {
    androidx.compose.foundation.lazy.LazyColumn(
        contentPadding = androidx.compose.foundation.layout.PaddingValues(20.dp),
        verticalArrangement = androidx.compose.foundation.layout.Arrangement.spacedBy(16.dp),
    ) {
        item { Title("¿Quién cobra hoy?") }
        item {
            Text(
                "Perfiles de demostración del servidor. Elegir una persona todavía no es iniciar sesión.",
                color = Muted,
                fontSize = 13.sp,
            )
        }
        items(s.bootstrap?.employees.orEmpty().size) { index ->
            val employee = s.bootstrap!!.employees[index]
            Action(
                title = employee.name + if (employee.role == "owner") " · Dueño" else " · Empleado",
                icon = Icons.Outlined.People,
            ) { vm.select(employee) }
        }
        if (s.bootstrap?.employees.isNullOrEmpty()) item { MutedText("El servidor no devolvió empleados.") }
        item { androidx.compose.material3.OutlinedButton(onClick = vm::refresh, enabled = !s.busy) { Text("Reintentar") } }
        item {
            MutedText("Próxima etapa: acceso real de dueño y empleados. Esta entrega sigue siendo un mockup sin autenticación.")
        }
    }
}
