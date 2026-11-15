package mx.abarpay.mobile

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * v3.1 · miniaturas de producto. El demo no tiene red: sus productos llegan sin
 * `imageUrl`, así que las filas del catálogo de Cobrar y la hoja del carrito deben
 * mostrar el emoji por categoría y no intentar cargar ninguna imagen.
 */
class ProductImageUiTest : AppUiTest() {
    @Test fun rowsAndCartSheetShowEmojiWhenProductHasNoImage() {
        openCheckout()
        val coca = model().ui.value.bootstrap!!.products.first { it.id == 1 }
        assertNull(coca.imageUrl)
        compose.onNodeWithTag("miniatura-producto-1").assertExists()
        compose.onNodeWithTag("emoji-producto-1").assertExists()
        compose.onNodeWithTag("imagen-producto-1").assertDoesNotExist()

        addProduct()
        compose.waitUntil(15_000) { model().ui.value.cart.any { it.productId == 1 } }
        compose.onNodeWithTag("ver-carrito").performClick()
        compose.onNodeWithTag("hoja-carrito").assertIsDisplayed()
        // La línea de la hoja repite la miniatura: dos emojis de Coca en pantalla.
        assertTrue(
            "La fila y la hoja deben mostrar el emoji de respaldo",
            compose.onAllNodesWithTag("emoji-producto-1").fetchSemanticsNodes().size >= 2,
        )
        compose.onNodeWithTag("imagen-producto-1").assertDoesNotExist()
        capture("11-miniaturas-emoji")
    }
}
