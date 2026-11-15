package mx.abarpay.mobile

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.onAllNodesWithContentDescription
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * v1.2.1 · carrito como hoja inferior: «Ver carrito» muestra líneas, subtotales y
 * controles grandes; «Seguir cobrando» cierra y «Cobrar» sigue abriendo la hoja de pago.
 */
class CartSheetUiTest : AppUiTest() {
    @Test fun cartSheetShowsLinesAndKeepsPaymentSheet() {
        openCheckout()
        addProduct(times = 2)
        compose.waitUntil(15_000) { model().ui.value.cart.any { it.productId == 1 && it.qtyMilli == 2000 } }

        compose.onNodeWithTag("ver-carrito").performClick()
        compose.onNodeWithTag("hoja-carrito").assertIsDisplayed()
        compose.onNodeWithText("Tu carrito").assertIsDisplayed()
        // Las líneas de la hoja se marcan igual que las filas: acento + check.
        assertTrue(
            "La hoja debe marcar las líneas del carrito con el check de acento",
            compose.onAllNodesWithContentDescription("En el carrito").fetchSemanticsNodes().size >= 2,
        )
        // Subtotal de la línea + total fijo de la hoja (y la barra detrás) con el mismo monto.
        assertTrue(
            "La hoja debe mostrar el subtotal y el total",
            compose.onAllNodesWithText("$36.00").fetchSemanticsNodes().size >= 2,
        )

        compose.onNodeWithTag("carrito-menos-1").performClick()
        compose.waitUntil(15_000) {
            model().ui.value.cart.find { it.productId == 1 }?.qtyMilli == 1000
        }
        compose.onNodeWithTag("carrito-mas-1").performClick()
        compose.waitUntil(15_000) {
            model().ui.value.cart.find { it.productId == 1 }?.qtyMilli == 2000
        }
        compose.onNodeWithTag("quitar-1").performClick()
        compose.waitUntil(15_000) { model().ui.value.cart.isEmpty() }
        compose.onNodeWithText("Tu carrito está vacío.").assertExists()

        compose.onNodeWithTag("seguir-cobrando").performClick()
        compose.waitUntil(15_000) {
            compose.onAllNodesWithTag("hoja-carrito").fetchSemanticsNodes().isEmpty()
        }

        // El botón «Cobrar» de la barra fija sigue abriendo la hoja de pago existente.
        addProduct()
        compose.waitUntil(15_000) { model().ui.value.cart.isNotEmpty() }
        compose.onNodeWithTag("abrir-pago").performClick()
        compose.onNodeWithText("Forma de pago").assertExists()
    }
}
