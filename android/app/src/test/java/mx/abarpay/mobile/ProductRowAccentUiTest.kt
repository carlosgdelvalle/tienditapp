package mx.abarpay.mobile

import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.SemanticsMatcher
import androidx.compose.ui.test.assert
import androidx.compose.ui.test.assertTextContains
import androidx.compose.ui.test.hasScrollToIndexAction
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performScrollToKey
import org.junit.Test

/**
 * v1.2.1 · fila acentuada con qty>0: borde/fondo de acento, check permanente,
 * píldora de cantidad animada y presets de cantidad intactos.
 */
class ProductRowAccentUiTest : AppUiTest() {
    @Test fun rowWithQuantityShowsAccentPillAndKeepsPresets() {
        openCheckout()
        compose.onNodeWithTag("fila-product-1")
            .assert(SemanticsMatcher.expectValue(SemanticsProperties.StateDescription, "sin agregar"))

        addProduct()
        compose.waitUntil(15_000) { model().ui.value.cart.any { it.productId == 1 && it.qtyMilli == 1000 } }
        compose.onNodeWithTag("fila-product-1")
            .assert(SemanticsMatcher.expectValue(SemanticsProperties.StateDescription, "en carrito"))
        compose.onNodeWithTag("qty-1").assertTextContains("1 pza")

        addProduct(times = 1)
        compose.waitUntil(15_000) { model().ui.value.cart.any { it.productId == 1 && it.qtyMilli == 2000 } }
        compose.onNodeWithTag("qty-1").assertTextContains("2 pza")
        capture("10-fila-acentuada")

        // Presets de cantidad por unidad siguen dentro de la fila (Huevo: kg).
        compose.onNode(hasScrollToIndexAction()).performScrollToKey("product-4")
        compose.onNodeWithTag("preset-4-2000").assertExists()
    }
}
