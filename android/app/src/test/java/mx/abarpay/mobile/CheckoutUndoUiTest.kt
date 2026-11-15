package mx.abarpay.mobile

import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.SemanticsMatcher
import androidx.compose.ui.test.assert
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertTextContains
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import org.junit.Test

/**
 * v1.2.1 · feedback al agregar: la fila se acenta, la píldora cambia y el aviso
 * «Deshacer» (~4 s) quita la última unidad agregada usando vm.quantity inverso.
 */
class CheckoutUndoUiTest : AppUiTest() {
    @Test fun addingShowsUndoAndUndoRemovesLastUnit() {
        openCheckout()
        addProduct()
        compose.waitUntil(15_000) { model().ui.value.cart.any { it.productId == 1 && it.qtyMilli == 1000 } }

        compose.onNodeWithTag("fila-product-1")
            .assert(SemanticsMatcher.expectValue(SemanticsProperties.StateDescription, "en carrito"))
        compose.onNodeWithTag("qty-1").assertTextContains("1 pza")
        compose.onNodeWithTag("aviso-deshacer").assertIsDisplayed()
        compose.onNodeWithTag("deshacer-agregado").assertIsDisplayed()
        capture("09-cobrar-agregado")

        compose.onNodeWithTag("deshacer-agregado").performClick()
        compose.waitUntil(15_000) { model().ui.value.cart.isEmpty() }
        compose.onNodeWithTag("aviso-deshacer").assertDoesNotExist()
        compose.onNodeWithTag("fila-product-1")
            .assert(SemanticsMatcher.expectValue(SemanticsProperties.StateDescription, "sin agregar"))
    }
}
