package mx.abarpay.mobile

import androidx.compose.ui.test.*
import org.junit.Test

class OwnerHomeUiTest : AppUiTest() {
    @Test fun ownerHomeShowsStatusCardsAndSettingsGear() {
        loginOwner()
        compose.onNodeWithTag("card-ventas").assertExists()
        compose.onNodeWithTag("card-fiado").assertExists()
        compose.onNodeWithTag("card-pendientes").assertExists()
        compose.onNodeWithTag("card-stock").assertExists()
        compose.onNodeWithText("Fiado de clientes").assertDoesNotExist()
        compose.onNodeWithTag("abrir-ajustes").performClick()
        compose.onNodeWithText("Ajustes").assertExists()
        compose.onNodeWithText("Tu tienda").assertExists()
    }
}
