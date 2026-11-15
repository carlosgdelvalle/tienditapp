package mx.abarpay.mobile

import android.media.AudioManager
import android.media.ToneGenerator
import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Add
import androidx.compose.material.icons.outlined.Check
import androidx.compose.material.icons.outlined.DeleteOutline
import androidx.compose.material.icons.outlined.Remove
import androidx.compose.material.icons.outlined.ShoppingCart
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilledTonalIconButton
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/**
 * UX de «Cobrar» (v1.2.1): filas escaneables del catálogo, feedback al agregar
 * (haptico/tono/píldora animada/aviso Deshacer) y carrito como hoja inferior.
 * El carrito sigue viviendo en [ShopState.cart]: aquí solo se dibuja.
 */

/** Fondo tintado de una fila con cantidad en el carrito. */
internal val CartTint = Color(0xFFF6EFFF)

/** Unidad recién agregada para el aviso «Deshacer» (token para reiniciar el aviso). */
internal data class UndoAdd(val productId: Int, val deltaMilli: Int, val token: Int)

/** Fila que acaba de agregarse: parpadea con el acento ~800 ms. */
internal data class FlashAdd(val productId: Int, val token: Int)

/** Emoji de la miniatura según la categoría del producto; 📦 si no hay coincidencia. */
internal fun categoryEmoji(category: String?): String {
    val key = category?.trim()?.lowercase().orEmpty()
    return when {
        key.isBlank() -> "📦"
        key.contains("bebida") || key.contains("refresco") || key.contains("agua") -> "🥤"
        key.contains("pan") -> "🍞"
        key.contains("abarrote") || key.contains("despensa") -> "🛒"
        key.contains("lácteo") || key.contains("lacteo") || key.contains("leche") -> "🥛"
        key.contains("botana") || key.contains("snack") -> "🍟"
        key.contains("dulce") || key.contains("golosina") -> "🍬"
        key.contains("embutido") || key.contains("carne") -> "🌭"
        key.contains("limpieza") -> "🧼"
        key.contains("corte") || key.contains("barber") -> "✂️"
        key.contains("manicure") || key.contains("uña") || key.contains("una") -> "💅"
        key.contains("comida") || key.contains("platillo") || key.contains("alimento") -> "🍽️"
        else -> "📦"
    }
}

/** Categoría visible de un producto: «Otro» cuando el catálogo no la trae. */
internal fun productCategory(product: Product): String =
    product.category?.takeIf { it.isNotBlank() } ?: "Otro"

/**
 * Feedback de agregar/quitar. El háptico es el que pide el dueño (LongPress) y el
 * tono es corto; todo va dentro de runCatching para que Robolectric (sin audio)
 * nunca rompa una prueba.
 */
internal class CartFeedback(
    private val haptics: androidx.compose.ui.hapticfeedback.HapticFeedback,
    private val tone: ToneGenerator?,
) {
    fun added() = play(ToneGenerator.TONE_PROP_BEEP)

    fun removed() = play(ToneGenerator.TONE_PROP_ACK)

    private fun play(type: Int) {
        runCatching { haptics.performHapticFeedback(HapticFeedbackType.LongPress) }
        runCatching { tone?.startTone(type, 45) }
    }
}

@Composable
internal fun rememberCartFeedback(): CartFeedback {
    val haptics = LocalHapticFeedback.current
    val tone = remember {
        runCatching { ToneGenerator(AudioManager.STREAM_MUSIC, 55) }.getOrNull()
    }
    DisposableEffect(tone) {
        onDispose { runCatching { tone?.release() } }
    }
    return remember(haptics, tone) { CartFeedback(haptics, tone) }
}

/** Encabezado pegajoso de una sección del catálogo (Rápidos / categoría). */
@Composable
internal fun CatalogSectionHeader(title: String, emoji: String? = null) {
    Surface(color = Lavender, modifier = Modifier.fillMaxWidth().testTag("seccion-$title")) {
        Row(
            Modifier.fillMaxWidth().padding(vertical = 6.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            if (emoji != null) Text(emoji, fontSize = 16.sp)
            Text(title, fontWeight = FontWeight.Bold, fontSize = 16.sp, color = Purple)
        }
    }
}

/** Aviso «Deshacer» tras agregar: ~4 s para quitar la última unidad agregada. */
@Composable
internal fun UndoAddBar(productName: String?, onUndo: () -> Unit) {
    Surface(
        color = Purple,
        shape = RoundedCornerShape(16.dp),
        modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 4.dp).testTag("aviso-deshacer"),
    ) {
        Row(
            Modifier.padding(start = 14.dp, end = 6.dp, top = 2.dp, bottom = 2.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text(
                if (productName.isNullOrBlank()) "Agregado a la venta" else "Agregado: $productName",
                color = Color.White,
                fontSize = 13.sp,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.weight(1f),
            )
            TextButton(
                onClick = onUndo,
                modifier = Modifier.testTag("deshacer-agregado"),
                colors = ButtonDefaults.textButtonColors(contentColor = Color.White),
                contentPadding = PaddingValues(horizontal = 12.dp, vertical = 6.dp),
            ) { Text("Deshacer", fontWeight = FontWeight.Bold) }
        }
    }
}

/** Fila escaneable del catálogo: miniatura, precio, existencias, stepper y presets. */
@Composable
internal fun CatalogProductRow(
    product: Product,
    qtyMilli: Int,
    flashing: Boolean,
    busy: Boolean,
    onAdd: () -> Unit,
    onRemove: () -> Unit,
    onOpenQuantity: () -> Unit,
    onSetPreset: (Int) -> Unit,
) {
    val inCart = qtyMilli > 0
    val background by animateColorAsState(
        targetValue = when {
            flashing -> SoftViolet
            inCart -> CartTint
            else -> Color.White
        },
        animationSpec = tween(durationMillis = 320),
        label = "fila-fondo",
    )
    val borderColor by animateColorAsState(
        targetValue = if (flashing || inCart) Violet else Color.Transparent,
        animationSpec = tween(durationMillis = 320),
        label = "fila-borde",
    )
    Surface(
        modifier = Modifier
            .fillMaxWidth()
            .testTag("fila-product-${product.id}")
            .semantics { stateDescription = if (inCart) "en carrito" else "sin agregar" },
        shape = RoundedCornerShape(20.dp),
        color = background,
        border = BorderStroke(if (flashing || inCart) 1.5.dp else 1.dp, borderColor),
    ) {
        Column(
            Modifier.padding(horizontal = 14.dp, vertical = 12.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                // v3.1 · imagen cuadrada del producto con caché; si no hay URL, emoji.
                ProductThumbnail(
                    product = product,
                    size = 46.dp,
                    background = if (inCart) SoftViolet else Lavender,
                )
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text(
                            product.name,
                            Modifier.weight(1f),
                            fontWeight = FontWeight.SemiBold,
                            fontSize = 16.sp,
                            maxLines = 2,
                            overflow = TextOverflow.Ellipsis,
                        )
                        Text(
                            money(product.priceCents),
                            fontWeight = FontWeight.Bold,
                            fontSize = 16.sp,
                            textAlign = TextAlign.End,
                        )
                    }
                    Text(
                        unitLabel(product.unit) + " · " + product.availableLabel +
                            if (product.isLowStock) " · " + COPY_LOW_STOCK else "",
                        color = if (product.isLowStock) Amber else Muted,
                        fontSize = 11.sp,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
            }
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                FilledTonalIconButton(
                    onClick = onRemove,
                    enabled = inCart && !busy,
                    modifier = Modifier.size(46.dp),
                ) { Icon(Icons.Outlined.Remove, "Quitar ${product.name}", Modifier.size(22.dp)) }
                QuantityPill(product = product, qtyMilli = qtyMilli, onClick = onOpenQuantity)
                FilledTonalIconButton(
                    onClick = onAdd,
                    enabled = !busy,
                    modifier = Modifier.size(46.dp),
                ) { Icon(Icons.Outlined.Add, "Agregar ${product.name}", Modifier.size(22.dp)) }
                if (inCart) {
                    Icon(Icons.Outlined.Check, "En el carrito", Modifier.size(20.dp), tint = Violet)
                }
                Spacer(Modifier.weight(1f))
                if (inCart) {
                    Text(
                        money(lineTotalCents(product.priceCents, qtyMilli)),
                        fontWeight = FontWeight.Bold,
                        fontSize = 14.sp,
                    )
                }
            }
            quantityPresets(product.unit)?.let { presets ->
                Row(
                    Modifier.horizontalScroll(rememberScrollState()),
                    horizontalArrangement = Arrangement.spacedBy(6.dp),
                ) {
                    presets.forEach { target ->
                        OutlinedButton(
                            onClick = { onSetPreset(target) },
                            enabled = !busy && target != qtyMilli,
                            contentPadding = PaddingValues(horizontal = 10.dp, vertical = 2.dp),
                            modifier = Modifier.testTag("preset-" + product.id + "-" + target),
                        ) { Text(quantityPresetLabel(target, product.unit)) }
                    }
                }
            }
        }
    }
}

/** Píldora de cantidad: acento cuando hay unidades en el carrito y animada al cambiar. */
@Composable
private fun QuantityPill(product: Product, qtyMilli: Int, onClick: () -> Unit) {
    val inCart = qtyMilli > 0
    val background by animateColorAsState(
        targetValue = if (inCart) Violet else Lavender,
        animationSpec = tween(durationMillis = 220),
        label = "pildora-fondo",
    )
    val content by animateColorAsState(
        targetValue = if (inCart) Color.White else Purple,
        animationSpec = tween(durationMillis = 220),
        label = "pildora-texto",
    )
    Box(
        Modifier
            .clip(RoundedCornerShape(50))
            .background(background)
            .clickable(onClick = onClick)
            .padding(horizontal = 14.dp, vertical = 9.dp)
            .widthIn(min = 58.dp)
            .testTag("qty-${product.id}"),
        contentAlignment = Alignment.Center,
    ) {
        AnimatedContent(targetState = qtyMilli, label = "pildora-cantidad") { value ->
            Text(
                qtyText(value, product.unit),
                color = content,
                fontWeight = FontWeight.Bold,
                fontSize = 13.sp,
                maxLines = 1,
                textAlign = TextAlign.Center,
            )
        }
    }
}

/** Barra fija: 🛒 conteo + total animados, «Ver carrito» y «Cobrar». */
@Composable
internal fun CartActionBar(
    itemCount: Int,
    total: Long,
    onVerCarrito: () -> Unit,
    onCobrar: () -> Unit,
) {
    Surface(tonalElevation = 6.dp) {
        Column(
            Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 10.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                Text("🛒", fontSize = 20.sp)
                AnimatedContent(targetState = itemCount, label = "conteo-carrito") { count ->
                    Text(
                        if (count == 1) "1 producto" else "$count productos",
                        color = Muted,
                        fontSize = 13.sp,
                    )
                }
                Spacer(Modifier.weight(1f))
                AnimatedContent(targetState = total, label = "total-carrito") { value ->
                    Text(money(value), fontWeight = FontWeight.Bold, fontSize = 24.sp)
                }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                OutlinedButton(
                    onClick = onVerCarrito,
                    enabled = itemCount > 0,
                    modifier = Modifier.weight(1f).heightIn(min = 50.dp).testTag("ver-carrito"),
                    shape = RoundedCornerShape(16.dp),
                ) {
                    Icon(Icons.Outlined.ShoppingCart, null, Modifier.size(18.dp))
                    Spacer(Modifier.width(6.dp))
                    Text("Ver carrito")
                }
                Button(
                    onClick = onCobrar,
                    enabled = itemCount > 0,
                    modifier = Modifier.weight(1f).heightIn(min = 52.dp).testTag("abrir-pago"),
                    shape = RoundedCornerShape(16.dp),
                ) { Text("Cobrar") }
            }
        }
    }
}

/** Hoja inferior del carrito: líneas marcadas con acento, +/− grandes, quitar y total fijo. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
internal fun CartSheet(
    lines: List<Pair<Product, CartLine>>,
    itemCount: Int,
    total: Long,
    busy: Boolean,
    onDismiss: () -> Unit,
    onDelta: (Product, Int) -> Unit,
    onRemoveLine: (Product, Int) -> Unit,
) {
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    ModalBottomSheet(onDismissRequest = onDismiss, sheetState = sheetState) {
        Column(
            Modifier
                .fillMaxWidth()
                .padding(start = 20.dp, end = 20.dp, bottom = 20.dp)
                .testTag("hoja-carrito"),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("Tu carrito", fontWeight = FontWeight.Bold, fontSize = 22.sp)
                Spacer(Modifier.weight(1f))
                Text(
                    if (itemCount == 1) "1 producto" else "$itemCount productos",
                    color = Muted,
                    fontSize = 13.sp,
                )
            }
            HorizontalDivider()
            if (lines.isEmpty()) {
                Text("Tu carrito está vacío.", color = Muted, fontSize = 14.sp)
            } else {
                Column(
                    Modifier.heightIn(max = 360.dp).verticalScroll(rememberScrollState()),
                    verticalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    lines.forEach { (product, line) ->
                        CartSheetLine(
                            product = product,
                            qtyMilli = line.qtyMilli,
                            busy = busy,
                            onDelta = { delta -> onDelta(product, delta) },
                            onRemove = { onRemoveLine(product, line.qtyMilli) },
                        )
                    }
                }
            }
            HorizontalDivider()
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("Total", fontWeight = FontWeight.SemiBold, fontSize = 16.sp)
                Spacer(Modifier.weight(1f))
                AnimatedContent(targetState = total, label = "total-hoja") { value ->
                    Text(money(value), fontWeight = FontWeight.Bold, fontSize = 26.sp)
                }
            }
            Button(
                onClick = onDismiss,
                modifier = Modifier.fillMaxWidth().heightIn(min = 56.dp).testTag("seguir-cobrando"),
                shape = RoundedCornerShape(16.dp),
            ) { Text("Seguir cobrando", fontSize = 17.sp) }
        }
    }
}

@Composable
private fun CartSheetLine(
    product: Product,
    qtyMilli: Int,
    busy: Boolean,
    onDelta: (Int) -> Unit,
    onRemove: () -> Unit,
) {
    val step = quantityStep(product.unit)
    Surface(
        color = CartTint,
        shape = RoundedCornerShape(18.dp),
        border = BorderStroke(1.5.dp, Violet),
    ) {
        Column(
            Modifier.fillMaxWidth().padding(12.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                // v3.1 · misma miniatura de la fila, un poco más chica en la hoja.
                ProductThumbnail(product = product, size = 40.dp, background = SoftViolet)
                Column(Modifier.weight(1f)) {
                    Text(
                        product.name,
                        fontWeight = FontWeight.SemiBold,
                        fontSize = 15.sp,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                    )
                    Text(
                        qtyText(qtyMilli, product.unit) + " × " + money(product.priceCents),
                        color = Muted,
                        fontSize = 12.sp,
                    )
                }
                Icon(Icons.Outlined.Check, "En el carrito", Modifier.size(18.dp), tint = Violet)
                Text(
                    money(lineTotalCents(product.priceCents, qtyMilli)),
                    fontWeight = FontWeight.Bold,
                    fontSize = 15.sp,
                )
            }
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                FilledTonalIconButton(
                    onClick = { onDelta(decrementStep(qtyMilli, step)) },
                    enabled = !busy,
                    modifier = Modifier.size(44.dp).testTag("carrito-menos-${product.id}"),
                ) { Icon(Icons.Outlined.Remove, "Quitar una unidad de ${product.name}", Modifier.size(20.dp)) }
                Text(
                    qtyText(qtyMilli, product.unit),
                    modifier = Modifier.widthIn(min = 62.dp),
                    textAlign = TextAlign.Center,
                    fontWeight = FontWeight.Bold,
                    fontSize = 14.sp,
                )
                FilledTonalIconButton(
                    onClick = { onDelta(step) },
                    enabled = !busy,
                    modifier = Modifier.size(44.dp).testTag("carrito-mas-${product.id}"),
                ) { Icon(Icons.Outlined.Add, "Agregar una unidad de ${product.name}", Modifier.size(20.dp)) }
                Spacer(Modifier.weight(1f))
                IconButton(
                    onClick = onRemove,
                    enabled = !busy,
                    modifier = Modifier.testTag("quitar-${product.id}"),
                ) { Icon(Icons.Outlined.DeleteOutline, "Quitar del carrito ${product.name}") }
            }
        }
    }
}

