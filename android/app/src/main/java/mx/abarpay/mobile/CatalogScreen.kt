package mx.abarpay.mobile

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material.icons.outlined.Search
import androidx.compose.material.icons.outlined.Star
import androidx.compose.material.icons.outlined.StarBorder
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
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
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/**
 * Catálogo del dueño (contrato v3): pantalla desde Inicio, no una pestaña.
 * Búsqueda, chips de categoría, favoritos/rápidos y LazyColumn para catálogos
 * grandes. Alta/edición con formulario y borrado con 409 controlado.
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
internal fun CatalogScreen(s: ShopState, vm: ShopViewModel) {
    var query by rememberSaveable { mutableStateOf("") }
    var category by rememberSaveable { mutableStateOf<String?>(null) }
    var kind by rememberSaveable { mutableStateOf<String?>(null) }
    var quickOnly by rememberSaveable { mutableStateOf(false) }
    var formOpen by rememberSaveable { mutableStateOf(false) }
    var editingId by rememberSaveable { mutableStateOf<Int?>(null) }
    var deletingId by rememberSaveable { mutableStateOf<Int?>(null) }

    val all = s.catalog?.items.orEmpty()
    val categories = catalogCategories(all)
    val visible = sortedCatalog(
        all.filter { catalogMatches(it, query, category, kind) && (!quickOnly || it.quick) },
    )
    val editing = editingId?.let { id -> all.firstOrNull { it.id == id } }

    deletingId?.let { id ->
        val item = all.firstOrNull { it.id == id }
        AlertDialog(
            onDismissRequest = { deletingId = null },
            title = { Text("¿Borrar del catálogo?") },
            text = {
                Text(
                    "Se borrará " + (item?.name ?: "el artículo") +
                        ". Si ya tiene ventas o movimientos, el servidor lo rechaza.",
                )
            },
            confirmButton = {
                TextButton(
                    onClick = { deletingId = null; vm.deleteCatalogItem(id) },
                    enabled = !s.busy,
                    modifier = Modifier.testTag("confirmar-borrar"),
                ) { Text("Sí, borrar") }
            },
            dismissButton = {
                TextButton(onClick = { deletingId = null }, enabled = !s.busy) { Text("Cancelar") }
            },
        )
    }

    LazyColumn(contentPadding = PaddingValues(20.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        item {
            TextButton(onClick = vm::closeCatalog, enabled = !s.busy) {
                Icon(Icons.AutoMirrored.Outlined.ArrowBack, null, Modifier.size(18.dp))
                Spacer(Modifier.width(8.dp))
                Text("Volver al inicio")
            }
        }
        item {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Title("Catálogo")
                Spacer(Modifier.weight(1f))
                TextButton(
                    onClick = { editingId = null; formOpen = !formOpen },
                    enabled = !s.busy,
                    modifier = Modifier.testTag("catalogo-nuevo"),
                ) { Text(if (formOpen) "Cerrar" else "Nuevo") }
            }
            MutedText("Búsqueda, categorías y favoritos. Los servicios y platillos no llevan inventario.")
        }
        if (formOpen) {
            item {
                CatalogForm(
                    item = editing,
                    busy = s.busy,
                    onCancel = { formOpen = false; editingId = null },
                    onSave = { draft ->
                        formOpen = false
                        val id = editing?.id
                        editingId = null
                        vm.saveCatalogItem(id, draft)
                    },
                )
            }
        }
        item {
            OutlinedTextField(
                query, { query = it },
                Modifier.fillMaxWidth().testTag("catalogo-buscar"),
                placeholder = { Text("Buscar por nombre o alias") },
                leadingIcon = { Icon(Icons.Outlined.Search, null) },
                singleLine = true,
                enabled = !s.busy,
                shape = RoundedCornerShape(28.dp),
            )
        }
        item {
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                FilterChip(
                    selected = category == null,
                    onClick = { category = null },
                    label = { Text("Todas") },
                    modifier = Modifier.testTag("categoria-todas"),
                )
                categories.forEach { name ->
                    FilterChip(
                        selected = category == name,
                        onClick = { category = if (category == name) null else name },
                        label = { Text(name) },
                        modifier = Modifier.testTag("categoria-" + name.lowercase().replace(' ', '-')),
                    )
                }
            }
        }
        item {
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                FilterChip(
                    selected = quickOnly,
                    onClick = { quickOnly = !quickOnly },
                    label = { Text("Rápidos") },
                    leadingIcon = { Icon(Icons.Outlined.Star, null, Modifier.size(16.dp)) },
                    modifier = Modifier.testTag("catalogo-rapidos"),
                )
                listOf(null to "Todos", KIND_PRODUCTO to "Productos", KIND_SERVICIO to "Servicios", KIND_PLATILLO to "Platillos")
                    .forEach { (value, label) ->
                        FilterChip(
                            selected = kind == value,
                            onClick = { kind = value },
                            label = { Text(label) },
                            modifier = Modifier.testTag("catalogo-kind-" + (value ?: "todos")),
                        )
                    }
            }
        }
        item {
            val total = s.catalog?.total ?: all.size
            MutedText("Mostrando " + visible.size + " de " + total + " artículos.")
        }
        if (visible.isEmpty()) {
            item { Text("No encontramos artículos con esos filtros.") }
        }
        items(visible, key = { "catalog-" + it.id }) { product ->
            Panel {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text(product.name, fontWeight = FontWeight.Bold)
                        Text(catalogItemSubtitle(product), color = Muted, fontSize = 12.sp)
                        if (product.aliases.isNotEmpty()) {
                            Text("Alias: " + aliasesText(product.aliases), color = Muted, fontSize = 11.sp)
                        }
                    }
                    IconButton(
                        onClick = {
                            val draft = catalogDraft(product).copy(quick = !product.quick)
                            vm.saveCatalogItem(product.id, draft)
                        },
                        enabled = !s.busy,
                        modifier = Modifier.testTag("rapido-" + product.id),
                    ) {
                        Icon(
                            if (product.quick) Icons.Outlined.Star else Icons.Outlined.StarBorder,
                            if (product.quick) "Quitar de rápidos" else "Marcar como rápido",
                        )
                    }
                }
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    OutlinedButton(
                        onClick = { editingId = product.id; formOpen = true },
                        enabled = !s.busy,
                        modifier = Modifier.weight(1f).testTag("editar-" + product.id),
                    ) { Text("Editar") }
                    TextButton(
                        onClick = { deletingId = product.id },
                        enabled = !s.busy,
                        modifier = Modifier.testTag("borrar-" + product.id),
                    ) { Text("Borrar") }
                }
            }
        }
    }
}

/** Formulario de alta/edición. Servicios y platillos ocultan los controles de stock. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun CatalogForm(
    item: Product?,
    busy: Boolean,
    onCancel: () -> Unit,
    onSave: (CatalogDraft) -> Unit,
) {
    val initial = item?.let(::catalogDraft) ?: CatalogDraft()
    var name by rememberSaveable(item?.id) { mutableStateOf(initial.name) }
    var price by rememberSaveable(item?.id) {
        mutableStateOf(if (initial.priceCents > 0) cashInputText(initial.priceCents) else "")
    }
    var unit by rememberSaveable(item?.id) { mutableStateOf(initial.unit) }
    var kind by rememberSaveable(item?.id) { mutableStateOf(initial.kind) }
    var category by rememberSaveable(item?.id) { mutableStateOf(initial.category.orEmpty()) }
    var stock by rememberSaveable(item?.id) {
        mutableStateOf(
            if (!initial.unlimitedStock && (initial.stockMilli ?: 0) > 0) qtyInputText(initial.stockMilli ?: 0) else "",
        )
    }
    var unlimited by rememberSaveable(item?.id) {
        mutableStateOf(initial.unlimitedStock || !kindTracksStock(initial.kind))
    }
    var duration by rememberSaveable(item?.id) {
        mutableStateOf(initial.durationMinutes?.toString().orEmpty())
    }
    var aliases by rememberSaveable(item?.id) { mutableStateOf(aliasesText(initial.aliases)) }
    var quick by rememberSaveable(item?.id) { mutableStateOf(initial.quick) }
    val tracksStock = kindTracksStock(kind) && !unlimited
    val draft = CatalogDraft(
        name = name,
        unit = unit,
        priceCents = parseCashCents(price) ?: 0,
        aliases = aliasesFrom(aliases),
        stockMilli = if (tracksStock) parseQtyMilli(stock) else null,
        unlimitedStock = unlimited || !kindTracksStock(kind),
        kind = kind,
        category = category.trim().ifBlank { null },
        durationMinutes = if (kind != KIND_PRODUCTO) duration.trim().toIntOrNull() else null,
        quick = quick,
    )
    Panel {
        Text(if (item == null) "Nuevo artículo" else "Editar artículo", fontWeight = FontWeight.Bold, fontSize = 17.sp)
        OutlinedTextField(
            name, { name = it },
            Modifier.fillMaxWidth().testTag("form-nombre"),
            label = { Text("Nombre") },
            singleLine = true,
            enabled = !busy,
            shape = RoundedCornerShape(16.dp),
        )
        OutlinedTextField(
            price, { price = it },
            Modifier.fillMaxWidth().testTag("form-precio"),
            label = { Text("Precio (MXN)") },
            placeholder = { Text("Ej. 25.00") },
            singleLine = true,
            enabled = !busy,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
            shape = RoundedCornerShape(16.dp),
        )
        Text("Unidad", fontWeight = FontWeight.SemiBold)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            PRODUCT_UNITS.forEach { option ->
                FilterChip(
                    selected = unit == option,
                    onClick = { unit = option },
                    enabled = !busy,
                    label = { Text(unitLabel(option)) },
                    modifier = Modifier.testTag("form-unidad-" + option),
                )
            }
        }
        Text("Tipo", fontWeight = FontWeight.SemiBold)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            PRODUCT_KINDS.forEach { option ->
                FilterChip(
                    selected = kind == option,
                    onClick = {
                        kind = option
                        if (!kindTracksStock(option)) unlimited = true
                    },
                    enabled = !busy,
                    label = { Text(kindLabel(option)) },
                    modifier = Modifier.testTag("form-kind-" + option),
                )
            }
        }
        OutlinedTextField(
            category, { category = it },
            Modifier.fillMaxWidth().testTag("form-categoria"),
            label = { Text("Categoría (opcional)") },
            singleLine = true,
            enabled = !busy,
            shape = RoundedCornerShape(16.dp),
        )
        if (kindTracksStock(kind)) {
            OutlinedTextField(
                stock, { stock = it },
                Modifier.fillMaxWidth().testTag("form-stock"),
                label = { Text("Existencia") },
                placeholder = { Text("Ej. 12 o 1.5") },
                singleLine = true,
                enabled = !busy && !unlimited,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                shape = RoundedCornerShape(16.dp),
            )
            Row(verticalAlignment = Alignment.CenterVertically) {
                Switch(
                    checked = unlimited,
                    onCheckedChange = { unlimited = it },
                    enabled = !busy,
                    modifier = Modifier.testTag("form-sinlimite"),
                )
                Spacer(Modifier.width(8.dp))
                Text("Sin límite de inventario", fontSize = 13.sp)
            }
        } else {
            MutedText("Los servicios y platillos no llevan inventario: no se piden existencias.", 12)
        }
        if (kind != KIND_PRODUCTO) {
            OutlinedTextField(
                duration, { duration = it },
                Modifier.fillMaxWidth().testTag("form-duracion"),
                label = { Text("Duración en minutos (opcional)") },
                singleLine = true,
                enabled = !busy,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                shape = RoundedCornerShape(16.dp),
            )
        }
        OutlinedTextField(
            aliases, { aliases = it },
            Modifier.fillMaxWidth().testTag("form-aliases"),
            label = { Text("Alias separados por coma") },
            placeholder = { Text("Ej. coca, refresco") },
            singleLine = true,
            enabled = !busy,
            shape = RoundedCornerShape(16.dp),
        )
        Row(verticalAlignment = Alignment.CenterVertically) {
            Checkbox(quick, { quick = it }, enabled = !busy, modifier = Modifier.testTag("form-rapido"))
            Spacer(Modifier.width(8.dp))
            Text("Mostrar en rápidos", fontSize = 13.sp)
        }
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Button(
                onClick = { onSave(draft) },
                enabled = !busy && catalogDraftReady(draft),
                modifier = Modifier.weight(1f).heightIn(min = 50.dp).testTag("form-guardar"),
                shape = RoundedCornerShape(16.dp),
            ) { Text(if (item == null) "Agregar" else "Guardar") }
            TextButton(onClick = onCancel, enabled = !busy) { Text("Cancelar") }
        }
    }
}
