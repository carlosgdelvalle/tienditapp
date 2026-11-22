package mx.abarpay.mobile

import androidx.compose.ui.test.assertIsSelected
import androidx.compose.ui.test.hasScrollToIndexAction
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollToKey
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * v1.2.1 · filas escaneables: chips de categoría sobre la lista, sección «Rápidos»
 * con encabezado pegajoso y miniatura por categoría.
 */
class CategoryChipsUiTest : AppUiTest() {
    @Test fun categoryChipsFilterCatalogAndKeepQuickSection() {
        loginOwner()
        compose.openDemoCheckout()
        compose.waitUntil(15_000) { model().ui.value.tab == TAB_SELL && !model().ui.value.busy }

        scrollToTag("cat-Todas").assertIsSelected()
        capture("12-categorias")
        compose.onNode(hasScrollToIndexAction()).performScrollToKey("product-1")
        assertTrue(
            "La fila de bebidas debe mostrar su miniatura 🥤",
            compose.onAllNodesWithText("🥤").fetchSemanticsNodes().isNotEmpty(),
        )
        compose.onNodeWithTag("seccion-Rápidos").assertExists()

        // Filtrar por categoría: el resto del catálogo deja de estar en la lista.
        scrollToTag("cat-Bebidas").performClick()
        compose.onNodeWithTag("cat-Bebidas").assertIsSelected()
        compose.onNodeWithText("Sabritas sal 45 g").assertDoesNotExist()
        compose.onNode(hasScrollToIndexAction()).performScrollToKey("product-1")
        compose.onNodeWithTag("seccion-Rápidos").assertExists()
        scrollToTag("seccion-Bebidas").assertExists()
        compose.onNodeWithTag("seccion-Botanas").assertDoesNotExist()

        // «Todas» restaura el catálogo completo.
        scrollToTag("cat-Todas").performClick()
        compose.onNodeWithTag("cat-Todas").assertIsSelected()
        compose.onNode(hasScrollToIndexAction()).performScrollToKey("product-2")
        compose.onNodeWithText("Sabritas sal 45 g").assertExists()
    }
}
