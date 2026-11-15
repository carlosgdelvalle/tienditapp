package mx.abarpay.mobile

import androidx.compose.ui.test.*
import org.junit.Test

/** Contrato v3 · copy genérico: «Tu negocio», «Inventario bajo», «disponibles»; «Fiado» intacto. */
class CopyV3UiTest : AppUiTest() {
    @Test fun homeAndInventoryUseGenericBusinessCopy() {
        loginOwner()
        compose.onNodeWithText("Tu negocio").assertExists()
        compose.onAllNodesWithText("Inventario bajo").fetchSemanticsNodes().let {
            org.junit.Assert.assertTrue("La tarjeta debe decir Inventario bajo", it.isNotEmpty())
        }
        compose.onNodeWithText("Tu tiendita").assertDoesNotExist()
        compose.onNodeWithText("Stock bajo").assertDoesNotExist()
        // «Fiado» se conserva tal cual.
        compose.onNodeWithTag("tab-Fiado").assertExists()
        compose.onNodeWithText("Fiado por cobrar").assertExists()
        // Badges de existencias con «disponibles».
        compose.onNodeWithTag("tab-Inventario").performClick()
        compose.waitUntil(15_000) { !model().ui.value.busy }
        scrollToText("24 unidades disponibles")
        compose.onNodeWithText("24 unidades disponibles").assertExists()
        compose.onNodeWithText("Inventario bajo").assertDoesNotExist()
    }
}
