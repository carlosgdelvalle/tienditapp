package mx.abarpay.mobile

import android.app.Application
import android.graphics.Bitmap
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

data class ShopState(
    val simulated: Boolean = true,
    val server: String = "",
    val bootstrap: Bootstrap? = null,
    val employee: Employee? = null,
    val report: Report? = null,
    val cart: List<CartLine> = emptyList(),
    val paymentMethod: String = PAYMENT_CASH,
    val customer: Customer? = null,
    val customers: List<Customer> = emptyList(),
    val customerDetail: CustomerDetail? = null,
    // Contrato v3.2 · historial del cliente abierto (cargo/abono, empleado, fecha).
    val fiadoEntries: List<FiadoEntry> = emptyList(),
    val sale: Sale? = null,
    val uncertain: Boolean = false,
    val busy: Boolean = false,
    val message: String? = null,
    val online: Boolean = true,
    val tab: String = TAB_HOME,
    val qrHidden: Boolean = false,
    val linkCode: String? = null,
    // Contrato v2: onboarding del dueño, identidad del empleado, equipo e inventario.
    val onboarded: Boolean = true,
    val ownerGoals: List<String> = emptyList(),
    val profile: StoreProfile? = null,
    val team: List<Employee>? = null,
    val teamOpen: Boolean = false,
    val invite: Invite? = null,
    val inviteToken: String? = null,
    val inviteInfo: InviteInfo? = null,
    val inviteError: String? = null,
    val voice: VoiceResult? = null,
    val inventory: InventorySnapshot? = null,
    val supportTicket: SupportTicket? = null,
    val linkedEmployeeId: Int? = null,
    // Contrato v3 · generalización a negocios pequeños.
    val ownerSells: List<String> = emptyList(),
    val catalog: CatalogPage? = null,
    val catalogOpen: Boolean = false,
    val tasks: List<DayTask>? = null,
    val tasksOpen: Boolean = false,
    val expenseDraft: ExpenseDraft? = null,
)

class ShopViewModel(app: Application) : AndroidViewModel(app) {
    private val prefs = app.getSharedPreferences("development_session", 0)

    /**
     * Onboarding, metas y perfil ligado viven fuera del diario del cobro para que
     * cambiar de servidor o de modo no borre la identidad del teléfono.
     */
    private val ownerPrefs = app.getSharedPreferences("abarpay_owner", 0)
    private var repo: ShopRepository = DemoRepository()
    // Cobros en efectivo sin conexión: outbox cifrado + replay al reconectar.
    private val coordinator = SaleCoordinator(app)
    private val state: MutableStateFlow<ShopState>
    val ui: StateFlow<ShopState>
    private var checking = false

    init {
        // Release: servidor de demo fijo y sin configuración manual. Debug: conserva
        // el servidor guardado o el modo simulación para las pruebas locales.
        val onboarded = ownerPrefs.getBoolean("onboarded_owner", false)
        val linked = ownerPrefs.getInt("employee_id", 0).takeIf { it > 0 }
        val goals = ownerPrefs.getString("owner_goals", "").orEmpty()
            .split("|").map { it.trim() }.filter { it.isNotBlank() }
        // «¿Qué vendes?» del onboarding v3: solo se guarda en este teléfono.
        val sells = ownerPrefs.getString("owner_sells", "").orEmpty()
            .split("|").map { it.trim() }.filter { it.isNotBlank() }
        val identity = ShopState(
            onboarded = onboarded || linked != null,
            ownerGoals = goals,
            ownerSells = sells,
            linkedEmployeeId = linked,
        )
        val server = if (BuildConfig.DEBUG) prefs.getString("server", "").orEmpty() else BuildConfig.DEMO_SERVER
        val (sale, uncertain) = recoverJournal(prefs.getString("sale", null), prefs.getBoolean("creating", false))
        state = MutableStateFlow(
            when {
                server.isNotBlank() -> identity.copy(
                    simulated = false, server = server, sale = sale, uncertain = uncertain,
                    qrHidden = prefs.getBoolean("qrHidden", false),
                )
                sale != null || uncertain -> identity.copy(
                    simulated = false, sale = sale, uncertain = true,
                    message = "No se pudo recuperar la conexión del cobro. No generes otro intento.",
                )
                else -> identity
            }
        )
        ui = state.asStateFlow()
        if (server.isNotBlank()) repo = ApiRepository(server)
        if (server.isNotBlank() || (!uncertain && sale == null)) refresh()
    }

    private fun work(action: suspend () -> Unit) {
        if (state.value.busy) return
        state.update { it.copy(busy = true, message = null) }
        viewModelScope.launch {
            try {
                action()
                state.update { it.copy(online = true) }
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                when (e) {
                    is IllegalStateException -> state.update { it.copy(message = e.message) }
                    is ApiFailure -> state.update { it.copy(message = e.message, online = true) }
                    else -> state.update { it.copy(message = null, online = false) }
                }
            } finally {
                state.update { it.copy(busy = false) }
            }
        }
    }

    fun refresh() = work { loadAll() }

    // -----------------------------------------------------------------------
    // Carga de datos y permisos del contrato v2
    // -----------------------------------------------------------------------

    private suspend fun loadAll() {
        val bootstrap = repo.bootstrap()
        val current = state.value
        // El perfil ligado se refresca desde el servidor para respetar cambios de permisos.
        var employee = current.employee?.let { selected ->
            bootstrap.employees.firstOrNull { it.id == selected.id } ?: selected
        } ?: current.linkedEmployeeId?.let { id -> bootstrap.employees.firstOrNull { it.id == id } }
        // En API el teléfono siempre queda ligado a una persona: tras el onboarding, el dueño
        // se enlaza automáticamente y el selector «¿Quién cobra hoy?» desaparece.
        if (!current.simulated && current.onboarded && employee == null) {
            employee = bootstrap.employees.firstOrNull { it.isOwner }?.also { owner ->
                ownerPrefs.edit().putInt("employee_id", owner.id).commit()
            }
        }
        repo.actAs(employee?.id)
        val isOwner = employee == null || employee.isOwner
        val report = if (canUseReports(employee)) runCatching { repo.report() }.getOrNull() else null
        val customers = runCatching { repo.customers() }.getOrNull()
        val profile = if (isOwner) runCatching { repo.profile() }.getOrNull() else null
        val team = if (isOwner) runCatching { repo.employees() }.getOrNull() else null
        val inventory = if (canUseInventory(employee)) runCatching { repo.inventory() }.getOrNull() else null
        // Tareas del día: el servidor solo manda las asignadas cuando hay X-Employee-Id.
        val tasks = runCatching { repo.tasks() }.getOrNull()
        state.update {
            it.copy(
                bootstrap = bootstrap,
                employee = employee,
                linkedEmployeeId = employee?.id ?: it.linkedEmployeeId,
                report = if (canUseReports(employee)) report ?: it.report else null,
                customers = customers ?: it.customers,
                profile = if (isOwner) profile ?: it.profile else null,
                team = if (isOwner) team ?: it.team else null,
                inventory = if (canUseInventory(employee)) inventory ?: it.inventory else null,
                tasks = if (isOwner || employee != null) tasks ?: it.tasks else it.tasks,
                tab = if (employee != null && !canUseTabs(employee, it.tab)) TAB_HOME else it.tab,
            )
        }
        // Renueva el arrendamiento sin conexión y, al volver a tener red, replica
        // las ventas pendientes del outbox (sin tocar el flujo en línea).
        syncOffline(bootstrap.store.id)
    }

    private suspend fun syncOffline(storeId: String) {
        val current = state.value
        if (current.simulated || current.server.isBlank()) return
        coordinator.attach(storeId)
        runCatching { coordinator.acquireLease(current.server) }
        val result = runCatching { coordinator.replay(current.server) }.getOrNull() ?: return
        if (result.sent == 0) return
        when {
            result.acked == result.sent -> message("Ventas sin conexión sincronizadas con el servidor.")
            result.rejected > 0 -> message("Algunas ventas quedaron por revisar al sincronizar.")
        }
    }

    private suspend fun loadSummary() {
        val bootstrap = runCatching { repo.bootstrap() }.getOrNull()
        val employee = state.value.employee
        val report = if (canUseReports(employee)) runCatching { repo.report() }.getOrNull() else null
        val customers = runCatching { repo.customers() }.getOrNull()
        val inventory = if (canUseInventory(employee)) runCatching { repo.inventory() }.getOrNull() else null
        val tasks = runCatching { repo.tasks() }.getOrNull()
        state.update {
            val fresh = bootstrap?.let { b -> employee?.let { e -> b.employees.firstOrNull { it.id == e.id } ?: e } }
            val actor = fresh ?: it.employee
            it.copy(
                bootstrap = bootstrap ?: it.bootstrap,
                employee = actor,
                report = if (canUseReports(actor)) report ?: it.report else null,
                customers = customers ?: it.customers,
                inventory = if (canUseInventory(actor)) inventory ?: it.inventory else null,
                tasks = tasks ?: it.tasks,
            )
        }
    }

    // -----------------------------------------------------------------------
    // Conexión, simulación y perfiles
    // -----------------------------------------------------------------------

    private fun resetState(simulated: Boolean, server: String) = ShopState(
        simulated = simulated,
        server = server,
        onboarded = state.value.onboarded,
        ownerGoals = state.value.ownerGoals,
        ownerSells = state.value.ownerSells,
        linkedEmployeeId = state.value.linkedEmployeeId,
        profile = state.value.profile,
        tasks = state.value.tasks,
    )

    fun connect(server: String) = work {
        check(state.value.sale == null && !state.value.uncertain) { "Resuelve el cobro actual antes de cambiar de servidor." }
        val normalized = normalizeServer(server, BuildConfig.DEBUG)
        val candidate = ApiRepository(normalized)
        val bootstrap = candidate.bootstrap()
        candidate.actAs(null)
        val report = candidate.report()
        val customers = runCatching { candidate.customers() }.getOrDefault(emptyList())
        check(prefs.edit().putString("server", normalized).commit()) { "No se pudo guardar la conexión" }
        repo = candidate
        state.value = resetState(simulated = false, server = normalized).copy(
            bootstrap = bootstrap,
            report = report,
            customers = customers,
        )
        loadAll()
    }

    fun useSimulation() = work {
        check(state.value.sale == null && !state.value.uncertain) { "Conservamos el cobro pendiente; revísalo antes de cambiar." }
        check(prefs.edit().clear().commit())
        val demo = DemoRepository()
        repo = demo
        demo.actAs(null)
        state.value = resetState(simulated = true, server = "")
        state.update {
            it.copy(
                bootstrap = demo.bootstrap(),
                report = demo.report(),
                customers = demo.customers(),
                inventory = runCatching { demo.inventory() }.getOrNull(),
            )
        }
    }

    fun select(employee: Employee) {
        if (state.value.busy) return
        repo.actAs(employee.id)
        state.update {
            it.copy(
                employee = employee, tab = TAB_HOME, message = null, customerDetail = null,
                fiadoEntries = emptyList(),
                teamOpen = false, invite = null, catalogOpen = false, tasksOpen = false,
            )
        }
        refresh()
    }

    fun leaveMockProfile() {
        val current = state.value
        if (!current.simulated || current.busy || current.sale != null || current.uncertain || current.cart.isNotEmpty()) return
        repo.actAs(null)
        state.update {
            it.copy(
                employee = null, tab = TAB_HOME, message = null, customer = null, customerDetail = null,
                fiadoEntries = emptyList(), catalogOpen = false, tasksOpen = false,
            )
        }
    }

    // -----------------------------------------------------------------------
    // Onboarding del dueño (solo primer arranque; metas solo locales)
    // -----------------------------------------------------------------------

    fun finishOnboarding(
        goals: List<String>,
        ownerName: String,
        storeName: String,
        businessType: String,
        photo: Bitmap?,
        sells: List<String> = emptyList(),
    ) = work {
        check(onboardingReady(ownerName, storeName, businessType)) {
            "Completa el nombre del dueño, el negocio y el tipo de negocio"
        }
        val updated = repo.updateProfile(
            name = storeName.trim(),
            businessType = businessType,
            ownerName = ownerName.trim(),
        )
        var notice: String? = null
        if (photo != null) {
            val dataUrl = withContext(Dispatchers.Default) { storePhotoDataUrl(photo) }
            runCatching { repo.uploadPhoto(dataUrl) }.onFailure { failure ->
                notice = "Tu negocio quedó guardado. La foto no se pudo subir: " + (failure.message ?: "")
            }
        }
        // v3: la plantilla del tipo de negocio solo aplica si la tienda aún no tenía
        // catálogo. Un 409 significa justo eso: se ignora y se conserva el catálogo.
        runCatching { repo.applyTemplate(templateBusinessType(businessType)) }.onFailure { failure ->
            if (!(failure is ApiFailure && failure.code == 409)) {
                notice = notice ?: ("Tu negocio quedó guardado. La plantilla no se pudo aplicar: " +
                    (failure.message ?: "revisa la conexión"))
            }
        }
        check(
            ownerPrefs.edit()
                .putBoolean("onboarded_owner", true)
                .putString("owner_goals", goals.joinToString("|"))
                .putString("owner_sells", sells.joinToString("|"))
                .commit()
        ) { "No se pudo guardar el onboarding en este teléfono" }
        // En API el onboarding enlaza al dueño con este teléfono; no vuelve a preguntar «¿Quién cobra hoy?».
        val owner = if (!state.value.simulated) {
            state.value.bootstrap?.employees?.firstOrNull { it.isOwner }?.also { linked ->
                ownerPrefs.edit().putInt("employee_id", linked.id).commit()
            }
        } else null
        state.update {
            it.copy(
                onboarded = true,
                ownerGoals = goals,
                ownerSells = sells,
                linkedEmployeeId = owner?.id ?: it.linkedEmployeeId,
                employee = owner ?: it.employee,
                profile = updated,
                message = notice ?: it.message,
                bootstrap = it.bootstrap?.copy(
                    store = it.bootstrap.store.copy(
                        name = updated.name,
                        businessType = updated.businessType,
                        ownerName = updated.ownerName,
                    ),
                ),
            )
        }
        loadAll()
    }

    // -----------------------------------------------------------------------
    // Catálogo del dueño (contrato v3 · pantalla desde Inicio, no una pestaña)
    // -----------------------------------------------------------------------

    fun openCatalog() = work {
        check(state.value.employee?.isOwner != false) { "Solo el dueño edita el catálogo" }
        val page = repo.catalog(limit = 500)
        state.update { it.copy(catalog = page, catalogOpen = true, message = null) }
    }

    fun closeCatalog() {
        state.update { it.copy(catalogOpen = false, message = null) }
    }

    fun saveCatalogItem(id: Int?, draft: CatalogDraft) = work {
        check(catalogDraftReady(draft)) { "Escribe el nombre y un precio mayor a cero" }
        val saved = if (id == null) repo.createCatalogItem(draft) else repo.updateCatalogItem(id, draft)
        state.update { s ->
            val current = s.catalog?.items.orEmpty()
            val next = if (current.any { it.id == saved.id }) {
                current.map { if (it.id == saved.id) saved else it }
            } else current + saved
            s.copy(
                catalog = CatalogPage(sortedCatalog(next), maxOf(next.size, s.catalog?.total ?: next.size)),
                message = if (id == null) "Agregado al catálogo: " + saved.name
                else "Catálogo actualizado: " + saved.name,
            )
        }
        runCatching { repo.catalog(limit = 500) }.getOrNull()?.let { page ->
            state.update { it.copy(catalog = page) }
        }
        loadSummary()
    }

    fun deleteCatalogItem(id: Int) = work {
        repo.deleteCatalogItem(id)
        state.update { s ->
            val remaining = s.catalog?.items.orEmpty().filterNot { it.id == id }
            s.copy(
                catalog = CatalogPage(sortedCatalog(remaining), maxOf(0, (s.catalog?.total ?: remaining.size) - 1)),
                message = "Artículo borrado del catálogo.",
            )
        }
        runCatching { repo.catalog(limit = 500) }.getOrNull()?.let { page ->
            state.update { it.copy(catalog = page) }
        }
        loadSummary()
    }

    // -----------------------------------------------------------------------
    // Tareas del día (dueño asigna; el empleado solo ve las suyas)
    // -----------------------------------------------------------------------

    fun openTasks() = work {
        check(state.value.employee?.isOwner != false) { "Solo el dueño asigna tareas" }
        val tasks = repo.tasks()
        state.update { it.copy(tasks = tasks, tasksOpen = true, message = null) }
    }

    fun closeTasks() {
        state.update { it.copy(tasksOpen = false, message = null) }
    }

    fun assignTask(id: Int, employeeId: Int?) = work {
        val updated = repo.patchTask(id, assignedEmployeeId = employeeId, clearAssignee = employeeId == null)
        state.update { s -> s.copy(tasks = s.tasks?.map { if (it.id == updated.id) updated else it }) }
    }

    fun setTaskActive(id: Int, active: Boolean) = work {
        val updated = repo.patchTask(id, active = active)
        state.update { s -> s.copy(tasks = s.tasks?.map { if (it.id == updated.id) updated else it }) }
    }

    // -----------------------------------------------------------------------
    // Gastos (dueño y empleado; dictado opcional)
    // -----------------------------------------------------------------------

    fun expenseVoice(text: String) = work {
        check(text.isNotBlank()) { "No escuchamos nada. Intenta de nuevo." }
        val draft = try {
            repo.expenseVoice(text.trim())
        } catch (e: ApiFailure) {
            if (e.code == 400 || e.code == 422) ExpenseDraft(0, "No entendí el monto. Escríbelo a mano.")
            else throw e
        }
        if (draft.amountCents <= 0) {
            message(draft.note ?: "No entendí el monto. Escríbelo a mano.")
        } else {
            state.update { it.copy(expenseDraft = draft, message = expenseVoiceMessage(draft)) }
        }
    }

    fun clearExpenseDraft() {
        state.update { it.copy(expenseDraft = null) }
    }

    fun addExpense(amountCents: Long, note: String?) = work {
        check(amountCents > 0) { "Escribe un monto mayor a cero" }
        val expense = repo.addExpense(amountCents, note?.trim()?.takeIf { it.isNotBlank() })
        state.update { it.copy(expenseDraft = null, message = expenseRegisteredMessage(expense.amountCents, expense.note)) }
        loadSummary()
    }

    // -----------------------------------------------------------------------
    // Equipo (dueño) e invitaciones
    // -----------------------------------------------------------------------

    fun openTeam() = work {
        check(canUseReports(state.value.employee)) { "Solo el dueño ve el equipo" }
        val team = repo.employees()
        state.update { it.copy(team = team, teamOpen = true, message = null) }
    }

    fun closeTeam() {
        state.update { it.copy(teamOpen = false, invite = null) }
    }

    fun patchEmployee(
        id: Int,
        name: String? = null,
        nickname: String? = null,
        active: Boolean? = null,
        canSell: Boolean? = null,
        canFiado: Boolean? = null,
        canInventory: Boolean? = null,
    ) = work {
        val updated = repo.patchEmployee(
            id = id, name = name, nickname = nickname, active = active,
            canSell = canSell, canFiado = canFiado, canInventory = canInventory,
        )
        state.update { s ->
            s.copy(team = s.team?.map { if (it.id == updated.id) updated else it })
        }
    }

    /** Devuelve la invitación con token y URL para el diálogo de QR. */
    fun createInvite(name: String, canSell: Boolean, canFiado: Boolean, canInventory: Boolean) = work {
        check(name.isNotBlank()) { "Escribe el nombre de la persona a invitar" }
        val invite = repo.createInvite(name.trim(), canSell, canFiado, canInventory)
        val team = runCatching { repo.employees() }.getOrNull()
        state.update { it.copy(invite = invite, team = team ?: it.team, message = null) }
    }

    fun closeInviteDialog() {
        state.update { it.copy(invite = null) }
    }

    /** Abre la pantalla «Ponle tu apodo» a partir del enlace profundo. */
    fun openInvite(token: String) {
        val clean = token.trim()
        if (clean.isBlank()) return
        viewModelScope.launch {
            state.update {
                it.copy(inviteToken = clean, inviteInfo = null, inviteError = null, message = null)
            }
            try {
                repo.actAs(null)
                val info = repo.inviteInfo(clean)
                state.update { it.copy(inviteInfo = info) }
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                state.update {
                    it.copy(inviteInfo = null, inviteError = e.message ?: "No pudimos abrir la invitación.")
                }
            }
        }
    }

    fun retryInvite() {
        val token = state.value.inviteToken ?: return
        openInvite(token)
    }

    fun dismissInvite() {
        state.update { it.copy(inviteToken = null, inviteInfo = null, inviteError = null) }
    }

    fun acceptInvite(nickname: String) = work {
        val token = state.value.inviteToken ?: error("No hay una invitación abierta")
        check(nickname.isNotBlank()) { "Escribe tu apodo" }
        val employee = repo.acceptInvite(token, nickname.trim())
        check(
            ownerPrefs.edit()
                .putInt("employee_id", employee.id)
                .putString("employee_nickname", employee.nickname.orEmpty())
                .commit()
        ) { "No se pudo guardar tu perfil en este teléfono" }
        repo.actAs(employee.id)
        val bootstrap = repo.bootstrap()
        val fresh = bootstrap.employees.firstOrNull { it.id == employee.id } ?: employee.copy(active = true)
        state.update {
            it.copy(
                inviteToken = null, inviteInfo = null, inviteError = null,
                linkedEmployeeId = fresh.id, employee = fresh, onboarded = true,
                tab = TAB_HOME, bootstrap = bootstrap,
                message = "Bienvenido al equipo de " + bootstrap.store.name + ".",
            )
        }
        loadAll()
    }

    // -----------------------------------------------------------------------
    // Inventario por voz (solo con can_inventory)
    // -----------------------------------------------------------------------

    fun voiceInventory(text: String) = work {
        check(canUseInventory(state.value.employee)) { "Tu perfil no puede editar el inventario" }
        check(text.isNotBlank()) { "No escuchamos nada. Intenta de nuevo." }
        val result = repo.inventoryVoice(text.trim())
        if (result.items.isEmpty()) {
            message(result.note ?: "No encontramos productos en ese dictado.")
        } else {
            state.update { it.copy(voice = result, message = result.note) }
        }
    }

    fun updateVoiceLine(productId: Int, qtyMilli: Int?) {
        state.update { s ->
            s.copy(voice = s.voice?.copy(items = s.voice.items.map {
                if (it.productId == productId) it.copy(qtyMilli = qtyMilli) else it
            }))
        }
    }

    fun closeVoice() {
        state.update { it.copy(voice = null) }
    }

    fun confirmVoice() = work {
        check(canUseInventory(state.value.employee)) { "Tu perfil no puede editar el inventario" }
        val lines = state.value.voice?.items.orEmpty()
        val toApply = lines.mapNotNull { line ->
            val qty = line.qtyMilli ?: return@mapNotNull null
            if (qty <= 0) null else line to qty
        }
        check(toApply.isNotEmpty()) { "Escribe cuántas piezas contaste" }
        var products = state.value.bootstrap?.products.orEmpty()
        toApply.forEach { (line, qty) ->
            val updated = repo.inventorySet(line.productId, qty, "conteo por voz")
            products = products.map { if (it.id == updated.id) updated else it }
        }
        state.update {
            it.copy(
                voice = null,
                bootstrap = it.bootstrap?.copy(products = products),
                message = "Inventario actualizado: " + toApply.joinToString(", ") { (line, qty) ->
                    line.name + " " + qtyText(qty, line.unit)
                },
            )
        }
        runCatching { loadSummary() }
    }

    // -----------------------------------------------------------------------
    // Tickets de soporte (cobros PEY que quedaron por conciliar)
    // -----------------------------------------------------------------------

    /**
     * Crea el ticket en el servidor (o recupera el que ya estaba abierto para
     * esa venta). El mensaje distingue «Ticket #… creado» de «Ya existe…».
     */
    fun reportTicket(saleId: String?, note: String?) = work {
        val ticket = repo.reportTicket(
            saleId = saleId?.trim()?.takeIf { it.isNotBlank() },
            note = note?.trim()?.takeIf { it.isNotBlank() },
        )
        state.update { it.copy(supportTicket = ticket, message = ticketMessage(ticket)) }
    }

    // -----------------------------------------------------------------------
    // Pestañas y cobro
    // -----------------------------------------------------------------------

    fun tab(value: String) {
        if (state.value.busy) return
        val employee = state.value.employee
        if (!canUseTabs(employee, value)) {
            message("Tu perfil no tiene acceso a la pestaña " + value + ".")
            return
        }
        state.update {
            it.copy(tab = value, message = null, teamOpen = false, catalogOpen = false, tasksOpen = false)
        }
        refresh()
    }

    fun message(value: String) {
        state.update { it.copy(message = value) }
    }

    fun setPaymentMethod(method: String) {
        if (state.value.busy || state.value.sale != null) return
        if (!canChoosePaymentMethod(state.value.employee, method)) {
            message("Tu perfil no tiene permiso de fiado.")
            return
        }
        state.update {
            it.copy(
                paymentMethod = method,
                customer = if (method == PAYMENT_FIADO) it.customer else null,
            )
        }
    }

    fun quantity(productId: Int, deltaMilli: Int) {
        if (state.value.busy || state.value.sale != null || state.value.uncertain) return
        runCatching { changeQuantity(state.value.cart, productId, deltaMilli) }
            .onSuccess { cart -> state.update { it.copy(cart = cart) } }
            .onFailure { message(it.message.orEmpty()) }
    }

    fun parse(text: String) = work {
        check(state.value.sale == null && !state.value.uncertain) { "Termina el cobro actual" }
        check(text.isNotBlank()) { "Escribe o dicta la venta" }
        val result = repo.parse(text.trim())
        var cart = state.value.cart
        result.items.forEach { line ->
            check(state.value.bootstrap?.products?.any { it.id == line.productId } == true) {
                "Producto desconocido. Actualiza el catálogo."
            }
            check(line.qtyMilli > 0) { "El servidor no devolvió una cantidad válida" }
            cart = changeQuantity(cart, line.productId, line.qtyMilli)
        }
        val unmatched = result.unmatched.takeIf { it.isNotEmpty() }
            ?.joinToString(prefix = "No encontré: ", separator = ", ")
        state.update {
            it.copy(
                cart = cart,
                message = listOfNotNull(
                    if (result.items.isEmpty()) "No encontramos productos en ese texto." else "Carrito actualizado.",
                    unmatched,
                    "Motor: " + result.engine,
                ).joinToString(" "),
            )
        }
    }

    fun lookup(code: String) = work {
        check(state.value.sale == null && !state.value.uncertain) { "Termina el cobro actual" }
        check(code.isNotBlank()) { "Escribe el código de barras" }
        try {
            val product = repo.lookup(code.trim())
            addToCart(product, 1000, "Agregado desde el código: " + product.name + ".")
        } catch (e: ApiFailure) {
            if (e.code == 404) {
                state.update { it.copy(linkCode = code.trim(), message = "Código sin enlazar. Elige el producto para guardarlo.") }
            } else {
                throw e
            }
        }
    }

    fun link(productId: Int) = work {
        val code = state.value.linkCode ?: return@work
        val product = repo.link(code, productId)
        state.update { it.copy(linkCode = null) }
        addToCart(product, 1000, "Código " + code + " enlazado a " + product.name + ".")
    }

    fun cancelLink() {
        state.update { it.copy(linkCode = null) }
    }

    private fun addToCart(product: Product, qtyMilli: Int, message: String) {
        val current = state.value
        check(current.bootstrap?.products?.any { it.id == product.id } == true) {
            "Actualiza el catálogo antes de agregar este producto."
        }
        state.update { it.copy(cart = changeQuantity(current.cart, product.id, qtyMilli), message = message) }
    }

    fun payCash(receivedCents: Long) {
        check(receivedCents > 0) { "Escribe el efectivo recibido" }
        submit(PAYMENT_CASH, receivedCents, null)
    }

    fun payPey() = submit(PAYMENT_PEY, null, null)

    fun payFiado() {
        if (!canChoosePaymentMethod(state.value.employee, PAYMENT_FIADO)) {
            message("Tu perfil no tiene permiso de fiado.")
            return
        }
        val customer = state.value.customer
        if (customer == null) {
            message("Elige o agrega un cliente para el fiado")
            return
        }
        submit(PAYMENT_FIADO, null, customer.id)
    }

    private fun submit(method: String, cashReceivedCents: Long?, customerId: Int?) {
        work {
            val snapshot = state.value
            check(snapshot.sale == null && !snapshot.uncertain && snapshot.cart.isNotEmpty()) {
                "El carrito está vacío"
            }
            check(canChoosePaymentMethod(snapshot.employee, method)) {
                "Tu perfil no tiene permiso para este tipo de cobro"
            }
            val employee = checkNotNull(snapshot.employee) { "Elige quién cobra" }
            val estimate = runCatching { cartEstimate(snapshot.cart, snapshot.bootstrap?.products.orEmpty()) }.getOrDefault(0)
            if (!snapshot.simulated) {
                check(prefs.edit().putBoolean("creating", true).commit()) {
                    "No se pudo proteger el intento. No se envió el cobro."
                }
            }
            state.update { it.copy(uncertain = true, message = null) }
            try {
                val created = repo.create(employee.id, snapshot.cart, method, cashReceivedCents, customerId)
                val sale = if (created.totalCents > 0) created else created.copy(
                    totalCents = estimate,
                    chargedCents = if (created.chargedCents > 0) created.chargedCents else estimate,
                )
                if (!snapshot.simulated && !persistSale(sale)) {
                    state.update { it.copy(sale = sale, uncertain = false, qrHidden = false) }
                    error("El cobro puede existir, pero no se pudo guardar. Revisa el servidor.")
                }
                state.update { it.copy(sale = sale, uncertain = false, qrHidden = false, linkCode = null) }
                if (sale.paymentMethod == PAYMENT_FIADO && sale.customerBalanceCents == null && sale.customerId != null) {
                    val detail = runCatching { repo.customer(sale.customerId) }.getOrNull()
                    if (detail != null) {
                        val updated = sale.copy(
                            customerName = detail.customer.name,
                            customerBalanceCents = detail.customer.balanceCents,
                        )
                        state.update { it.copy(sale = updated) }
                        if (!snapshot.simulated) persistSale(updated)
                    }
                }
                loadSummary()
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                if (e is ApiFailure && definitelyRejected(e.code)) {
                    if (snapshot.simulated || prefs.edit().putBoolean("creating", false).commit()) {
                        state.update { it.copy(uncertain = false) }
                    }
                    throw e
                }
                // Servidor inalcanzable (no hubo respuesta HTTP): una venta en
                // efectivo se finaliza en el teléfono y se sincroniza al reconectar.
                if (method == PAYMENT_CASH && !snapshot.simulated && e !is ApiFailure) {
                    finalizeOfflineCashSale(snapshot, employee, estimate, cashReceivedCents)
                    return@work
                }
                throw e
            }
        }
    }

    private fun finalizeOfflineCashSale(snapshot: ShopState, employee: Employee, totalCents: Long, cashReceivedCents: Long?) {
        val storeId = snapshot.bootstrap?.store?.id.orEmpty()
        check(storeId.isNotBlank()) { "Actualiza el catálogo antes de vender sin conexión" }
        coordinator.attach(storeId)
        coordinator.offlineBlocker()?.let { reason ->
            prefs.edit().putBoolean("creating", false).commit()
            state.update { it.copy(uncertain = false) }
            error(reason)
        }
        snapshot.bootstrap?.products?.let { coordinator.seedLocalStock(it) }
        val received = cashReceivedCents ?: totalCents
        val catalogVersion = coordinator.snapshot()?.catalogVersion ?: 0L
        val result = coordinator.finalizeOfflineCashSale(
            employeeId = employee.id,
            cart = snapshot.cart,
            totalCents = totalCents,
            cashReceivedCents = received,
            catalogVersion = catalogVersion,
        )
        val sale = Sale(
            id = result.reference,
            totalCents = result.totalCents,
            chargedCents = received,
            status = "paid_cash",
            paymentMethod = PAYMENT_CASH,
            cashReceivedCents = received,
            changeCents = received - result.totalCents,
            note = "Guardada en el teléfono. Se sincronizará al reconectar.",
            createdAt = System.currentTimeMillis() / 1000.0,
        )
        if (!persistSale(sale)) {
            state.update { it.copy(uncertain = false) }
            error("La venta se guardó en el teléfono, pero no se pudo proteger el comprobante.")
        }
        prefs.edit().putBoolean("creating", false).commit()
        state.update {
            it.copy(
                sale = sale,
                uncertain = false,
                qrHidden = false,
                linkCode = null,
                message = "Venta guardada sin conexión. Se sincronizará al reconectar.",
            )
        }
    }

    suspend fun poll() {
        val current = state.value.sale ?: return
        if (checking || state.value.busy) return
        if (current.paymentMethod != PAYMENT_PEY) return
        if (current.status !in setOf("pending", "por_conciliar", "expired")) return
        if (!state.value.simulated && state.value.server.isBlank()) return
        checking = true
        try {
            val remote = repo.status(current.id)
            val merged = remote.copy(
                qrImage = remote.qrImage.ifBlank { current.qrImage },
                qrId = remote.qrId ?: current.qrId,
                expiresAt = if (remote.expiresAt > 0.0) remote.expiresAt else current.expiresAt,
                totalCents = if (remote.totalCents > 0) remote.totalCents else current.totalCents,
                chargedCents = if (remote.chargedCents > 0) remote.chargedCents else current.chargedCents,
            )
            if (state.value.busy || state.value.sale?.status == "canceled" ||
                state.value.sale?.id != merged.id || state.value.sale?.settled == true) return
            if (!state.value.simulated) persistSale(merged)
            val becameSettled = merged.settled
            state.update { it.copy(sale = merged, message = null) }
            if (becameSettled) loadSummary()
        } catch (e: CancellationException) {
            throw e
        } catch (_: Exception) {
            state.update {
                it.copy(message = "Sin confirmación del servidor. No vuelvas a cobrar; retomaremos la consulta al conectar.")
            }
        } finally {
            checking = false
        }
    }

    fun checkNow() {
        viewModelScope.launch { poll() }
    }

    fun cancelPeySale() = work {
        val snapshot = state.value
        val current = snapshot.sale ?: return@work
        if (!current.canCancelPey) return@work
        if (!snapshot.simulated && snapshot.server.isBlank()) {
            message("Conservamos el cobro. Recupera la conexión para cancelarlo.")
            return@work
        }
        try {
            val result = repo.cancel(current.id)
            check(result.id == current.id && result.status == "canceled")
            if (!state.value.simulated) persistSale(result)
            state.update { it.copy(sale = result, qrHidden = true, message = "Venta cancelada. No se devolvió dinero.") }
            runCatching { loadSummary() }
        } catch (e: ApiFailure) {
            if (e.code != 409) throw e
            val remote = repo.status(current.id)
            if (!state.value.simulated) persistSale(remote)
            state.update { it.copy(sale = remote, message = "El cobro cambió de estado; no se canceló.") }
            runCatching { loadSummary() }
        } catch (e: CancellationException) {
            throw e
        } catch (_: Exception) {
            message("No se confirmó la cancelación. Conservamos el cobro; consulta su estado antes de volver a cobrar.")
        }
    }

    fun simulatePayment() = work {
        val sale = state.value.sale ?: return@work
        val demo = repo as? DemoRepository ?: error("La confirmación simulada solo existe en modo simulación")
        demo.simulatePaid(sale)
        val updated = demo.status(sale.id)
        val merged = updated.copy(
            qrImage = updated.qrImage.ifBlank { sale.qrImage },
            expiresAt = if (updated.expiresAt > 0.0) updated.expiresAt else sale.expiresAt,
            totalCents = if (updated.totalCents > 0) updated.totalCents else sale.totalCents,
            chargedCents = if (updated.chargedCents > 0) updated.chargedCents else sale.chargedCents,
        )
        state.update { it.copy(sale = merged, message = "Confirmación SIMULADA. No hubo pago.") }
        loadSummary()
    }

    /**
     * Solo simulación (QA): deja el cobro PEY actual en «por_conciliar» para
     * probar el botón «Reportar problema» sin red ni dinero. No tiene botón.
     */
    internal fun simulateUnconfirmed() = work {
        check(state.value.simulated) { "La conciliación simulada solo existe sin conexión" }
        val sale = state.value.sale ?: return@work
        val demo = repo as? DemoRepository ?: error("La conciliación simulada solo existe en modo simulación")
        demo.simulateUnconfirmed(sale)
        val updated = demo.status(sale.id)
        state.update {
            it.copy(
                sale = updated.copy(qrImage = updated.qrImage.ifBlank { sale.qrImage }),
                message = "Cobro SIMULADO por conciliar. No hubo pago.",
            )
        }
    }

    fun hideQr() = work {
        checkNotNull(state.value.sale)
        if (!state.value.simulated) check(prefs.edit().putBoolean("qrHidden", true).commit())
        state.update {
            it.copy(
                qrHidden = true,
                message = "QR oculto en este teléfono. No se canceló el cobro; conservamos la venta para consultar pagos tardíos.",
            )
        }
    }

    fun newSale() {
        val current = state.value
        if (current.busy || current.sale?.settled != true) return
        if (!current.simulated && !prefs.edit().remove("sale").putBoolean("qrHidden", false).commit()) {
            message("No se pudo guardar. Conservamos la venta.")
            return
        }
        state.update {
            it.copy(
                sale = null, cart = emptyList(), customer = null, tab = TAB_SELL,
                qrHidden = false, supportTicket = null, message = "Listo para el siguiente cobro.",
            )
        }
        refresh()
    }

    fun dismissSale() {
        val current = state.value
        if (current.busy) return
        val sale = current.sale ?: return
        if (!sale.settled && sale.status != "failed" && sale.status != "canceled" && sale.status != "expired") return
        if (!current.simulated) prefs.edit().remove("sale").putBoolean("qrHidden", false).commit()
        state.update { it.copy(sale = null, tab = TAB_SELL, qrHidden = false) }
        refresh()
    }

    fun selectCustomer(customer: Customer) {
        if (state.value.busy) return
        state.update { it.copy(customer = customer) }
    }

    fun addCustomer(name: String, phone: String) = work {
        check(name.isNotBlank()) { "Escribe el nombre del cliente" }
        val customer = repo.addCustomer(name.trim(), phone.trim().ifBlank { null })
        state.update {
            it.copy(
                customers = (it.customers.filterNot { c -> c.id == customer.id } + customer)
                    .sortedBy { c -> c.name.lowercase() },
                customer = if (it.paymentMethod == PAYMENT_FIADO) customer else it.customer,
                message = "Cliente " + customer.name + " agregado.",
            )
        }
    }

    fun openCustomer(id: Int) = work {
        val detail = repo.customer(id)
        state.update { it.copy(customerDetail = detail, fiadoEntries = loadFiadoEntries(id, detail)) }
    }

    fun closeCustomer() {
        state.update { it.copy(customerDetail = null, fiadoEntries = emptyList()) }
    }

    fun abono(amountCents: Long, note: String) = work {
        val detail = state.value.customerDetail ?: error("Elige un cliente")
        check(amountCents > 0) { "Escribe un monto mayor a cero" }
        val employee = checkNotNull(state.value.employee) { "Elige quién registra el abono" }
        repo.abono(detail.customer.id, amountCents, employee.id, note.trim().ifBlank { null })
        val refreshed = repo.customer(detail.customer.id)
        state.update {
            it.copy(
                customerDetail = refreshed,
                fiadoEntries = loadFiadoEntries(detail.customer.id, refreshed),
                customers = it.customers.map { c -> if (c.id == refreshed.customer.id) refreshed.customer else c },
                customer = if (it.customer?.id == refreshed.customer.id) refreshed.customer else it.customer,
                message = "Abono registrado. Saldo: " + money(refreshed.customer.balanceCents) + ".",
            )
        }
        loadSummary()
    }

    /**
     * Historial con nombres vía /entries. El servidor lo reserva a dueño o canFiado,
     * así que un empleado sin permiso conserva el historial que trae el detalle del
     * cliente (saldo e historial visibles, controles de abono ocultos).
     */
    private suspend fun loadFiadoEntries(customerId: Int, detail: CustomerDetail): List<FiadoEntry> =
        try {
            repo.fiadoEntries(customerId)
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            detail.entries
        }

    fun adjust(productId: Int, deltaMilli: Int) = work {
        check(canUseInventory(state.value.employee)) { "Tu perfil no puede editar el inventario" }
        val employee = checkNotNull(state.value.employee) { "Elige quién cobra" }
        val updated = repo.adjust(employee.id, productId, deltaMilli, "conteo")
        state.update { s ->
            s.copy(
                bootstrap = s.bootstrap?.copy(
                    products = s.bootstrap.products.map { if (it.id == updated.id) updated else it },
                ),
                message = "Ajuste guardado: " + updated.name + " ahora tiene " + qtyText(updated.stockMilli, updated.unit) + ".",
            )
        }
        runCatching { loadSummary() }
    }

    private fun persistSale(sale: Sale): Boolean {
        val safe = if (sale.qrImage.length > 2_000_000) sale.copy(qrImage = "") else sale
        return prefs.edit()
            .putString("sale", saleJson(safe).toString())
            .putBoolean("creating", false)
            .commit()
    }
}
