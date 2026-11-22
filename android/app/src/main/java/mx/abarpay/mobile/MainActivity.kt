package mx.abarpay.mobile

import android.content.Intent
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
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.BarChart
import androidx.compose.material.icons.outlined.Home
import androidx.compose.material.icons.outlined.Inventory2
import androidx.compose.material.icons.outlined.People
import androidx.compose.material.icons.outlined.PointOfSale
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.TextButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.repeatOnLifecycle
import androidx.core.splashscreen.SplashScreen.Companion.installSplashScreen
import androidx.lifecycle.viewmodel.compose.viewModel
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {
    /** Token de abarpay://empleado/<token> o https://…/invite/<token>. */
    private var deepLink by mutableStateOf<String?>(null)
    private var showOwnerApproval by mutableStateOf(false)
    private var openOwnerCash by mutableStateOf(false)
    private var employeeInvite by mutableStateOf<String?>(null)
    private var linkedEmployee by mutableStateOf(false)
    private val employeePrefs by lazy { getSharedPreferences("abarpay_employee_entry", MODE_PRIVATE) }
    private val ownerAuth: OwnerAuth by lazy {
        OwnerPhoneAuth(applicationContext, BuildConfig.OWNER_API_BASE_URL)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        installSplashScreen()
        enableEdgeToEdge()
        showOwnerApproval = savedInstanceState?.getBoolean("ownerApproval") == true
        openOwnerCash = savedInstanceState?.getBoolean("ownerCash") == true
        linkedEmployee = ownerConfigured && employeePrefs.getBoolean("linked", false)
        handleIncomingIntent(intent)
        setContent {
            var splashDone by remember { mutableStateOf(BuildConfig.DEBUG) }
            if (!splashDone) {
                SplashGate(onDone = { splashDone = true })
                return@setContent
            }
            AbarpayTheme {
                Box(Modifier.fillMaxSize()) {
                    val invitation = employeeInvite
                    if (invitation != null) {
                        key(invitation) {
                            OwnerQrApprovalScreen(
                                ownerAuth = ownerAuth,
                                apiBaseUrl = BuildConfig.OWNER_API_BASE_URL,
                                onClose = ::clearEmployeeInvitation,
                                employeeInvitation = invitation,
                                onEmployeeJoined = {
                                    check(employeePrefs.edit().putBoolean("linked", true).commit())
                                    linkedEmployee = true
                                    clearEmployeeInvitation()
                                },
                            )
                        }
                    } else if (linkedEmployee) {
                        EmployeeWorkspace(ownerAuth, BuildConfig.OWNER_API_BASE_URL)
                    } else if (showOwnerApproval || openOwnerCash) {
                        OwnerQrApprovalScreen(
                            ownerAuth = ownerAuth,
                            apiBaseUrl = BuildConfig.OWNER_API_BASE_URL,
                            onClose = { showOwnerApproval = false; openOwnerCash = false },
                            startInCash = openOwnerCash,
                        )
                    } else {
                        val model: ShopViewModel = viewModel()
                        val state by model.ui.collectAsStateWithLifecycle()
                        var scanning by rememberSaveable { mutableStateOf(false) }
                        val pendingInvite = deepLink
                        LaunchedEffect(pendingInvite) {
                            if (pendingInvite != null) {
                                deepLink = null
                                model.openInvite(pendingInvite)
                            }
                        }
                        AbarpayApp(
                            state, model, scan = { scanning = true },
                            openOwner = if (ownerConfigured) ({ showOwnerApproval = true }) else null,
                            openCash = if (ownerConfigured) ({ openOwnerCash = true }) else null,
                        )
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

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        handleIncomingIntent(intent)
    }

    override fun onSaveInstanceState(outState: Bundle) {
        outState.putBoolean("ownerApproval", showOwnerApproval)
        outState.putBoolean("ownerCash", openOwnerCash)
        super.onSaveInstanceState(outState)
    }

    private val ownerConfigured: Boolean
        get() = BuildConfig.OWNER_API_BASE_URL.isNotBlank()

    private fun clearEmployeeInvitation() {
        employeeInvite = null
        setIntent(Intent(this, MainActivity::class.java))
    }

    private fun handleIncomingIntent(intent: Intent?) {
        val data = intent?.data
        if (ownerConfigured && data != null) {
            val server = android.net.Uri.parse(BuildConfig.OWNER_API_BASE_URL)
            val token = when {
                data.scheme == "abarpay" && data.host == "equipo" && data.pathSegments.size == 1 ->
                    data.lastPathSegment
                data.scheme == "https" && data.host == server.host && data.pathSegments.size == 2 &&
                    data.port == server.port && data.pathSegments.first() == "invite" -> data.lastPathSegment
                else -> null
            }
            if (token != null && token.matches(Regex("^[A-Za-z0-9_-]{4,128}$"))) {
                showOwnerApproval = false
                openOwnerCash = false
                employeeInvite = token
                return
            }
        }
        if (data != null && data.scheme == "abarpay" && data.host == "dueno") {
            if (ownerConfigured) {
                openOwnerCash = false
                showOwnerApproval = true
            }
            return
        }
        extractInviteToken(intent?.dataString)?.let { deepLink = it }
    }
}

@Composable
private fun AbarpayApp(s: ShopState, vm: ShopViewModel, scan: () -> Unit, openOwner: (() -> Unit)?, openCash: (() -> Unit)?) {
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

    BackHandler(
        enabled = settings || s.teamOpen || s.catalogOpen || s.tasksOpen || s.inviteToken != null ||
            s.customerDetail != null || s.sale != null || s.uncertain || s.tab != TAB_HOME,
    ) {
        when {
            s.inviteToken != null -> vm.dismissInvite()
            settings -> settings = false
            s.catalogOpen -> vm.closeCatalog()
            s.tasksOpen -> vm.closeTasks()
            s.teamOpen -> vm.closeTeam()
            s.customerDetail != null -> vm.closeCustomer()
            s.sale != null || s.uncertain ->
                vm.message("Conservamos el cobro. Consultar o salir de la app no confirma ni cancela el pago.")
            else -> vm.tab(TAB_HOME)
        }
    }

    Scaffold(
        containerColor = Purple,
        bottomBar = {
            val tabs = tabsFor(s.employee)
            val showTabs = !settings && s.employee != null && s.sale == null && !s.uncertain &&
                !s.teamOpen && !s.catalogOpen && !s.tasksOpen && s.inviteToken == null
            if (showTabs) {
                NavigationBar(containerColor = Color.White) {
                    tabs.forEach { label ->
                        NavigationBarItem(
                            selected = s.tab == label,
                            onClick = { vm.tab(label) },
                            enabled = !s.busy,
                            modifier = Modifier.testTag("tab-" + label),
                            icon = { Icon(tabIcon(label), label) },
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
                CompactHeader(onOwner = openOwner, onCash = openCash)
                if (s.busy) LinearProgressIndicator(Modifier.fillMaxWidth())
                Notice(
                    when {
                        s.simulated -> "SIMULADO · Sin dinero real"
                        s.bootstrap?.demoMode == true -> "MODO DEMO · PEY cobra $0.01 MXN"
                        else -> "DESARROLLO · API sin autenticación"
                    },
                    warning = !s.simulated,
                )
                if (!s.online) Notice("Sin conexión. Los cobros en línea están desactivados hasta que se restablezca la conexión.", true)
                s.message?.let { Notice(it, true) }
                when {
                    s.inviteToken != null -> InviteAcceptScreen(s, vm)
                    settings -> SettingsScreen(s, vm) { settings = false }
                    !s.busy && (s.uncertain || (!s.simulated && s.server.isBlank())) -> UncertainScreen(s.sale?.id)
                    s.sale != null -> SaleScreen(s, vm)
                    s.bootstrap == null -> ConnectingScreen(s, vm) { settings = true }
                    s.catalogOpen -> CatalogScreen(s, vm)
                    s.tasksOpen -> TasksScreen(s, vm)
                    s.teamOpen -> TeamScreen(s, vm)
                    s.employee == null && !s.onboarded -> OnboardingScreen(s, vm)
                    s.employee == null && s.simulated -> AccessMockups(s, vm::select)
                    s.employee == null -> NoProfileScreen(s, vm)
                    s.tab == TAB_HOME -> HomeScreen(s, vm) { settings = true }
                    s.tab == TAB_SELL -> CheckoutScreen(s, vm, scan)
                    s.tab == TAB_FIADO -> FiadoScreen(s, vm)
                    s.tab == TAB_INVENTORY -> InventoryScreen(s, vm)
                    else -> ReportsScreen(s, vm)
                }
            }
        }
    }
}

/** Encabezado compacto: solo el logo pequeño dentro del contenido, sin nombre ni URL. */
@Composable
private fun CompactHeader(onOwner: (() -> Unit)?, onCash: (() -> Unit)?) {
    Row(
        Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Surface(shape = RoundedCornerShape(10.dp), color = Color.White) {
            Image(
                painterResource(R.drawable.abarpay_logo),
                "Abarpay",
                Modifier.padding(horizontal = 8.dp, vertical = 5.dp).width(58.dp).height(19.dp),
            )
        }
        Spacer(Modifier.weight(1f))
        if (onCash != null) {
            TextButton(onClick = onCash, modifier = Modifier.testTag("owner-cash-entry")) {
                Text("Caja")
            }
        }
        if (onOwner != null) {
            TextButton(onClick = onOwner, modifier = Modifier.testTag("owner-entry")) {
                Text("Consola", fontSize = 12.sp)
            }
        }
    }
}

private fun tabIcon(label: String): ImageVector = when (label) {
    TAB_SELL -> Icons.Outlined.PointOfSale
    TAB_FIADO -> Icons.Outlined.People
    TAB_INVENTORY -> Icons.Outlined.Inventory2
    TAB_REPORTS -> Icons.Outlined.BarChart
    else -> Icons.Outlined.Home
}

@Composable
private fun NoProfileScreen(s: ShopState, vm: ShopViewModel) {
    androidx.compose.foundation.lazy.LazyColumn(
        contentPadding = androidx.compose.foundation.layout.PaddingValues(20.dp),
        verticalArrangement = androidx.compose.foundation.layout.Arrangement.spacedBy(16.dp),
    ) {
        item { Title("Conecta tu perfil") }
        item {
            Text(
                "Este teléfono no tiene un perfil enlazado. Si te invitaron, abre el enlace o el QR que te compartieron y la app se abrirá sola para que elijas tu apodo.",
                color = Muted,
                fontSize = 13.sp,
            )
        }
        item {
            androidx.compose.material3.OutlinedButton(onClick = vm::refresh, enabled = !s.busy) {
                Text("Reintentar")
            }
        }
    }
}
