package mx.abarpay.mobile

import androidx.compose.ui.test.*
import org.junit.Test

class OwnerHomeUiTest : AppUiTest() {
    @Test fun ownerHomeShowsStatusCardsAndSettingsGear() {
        loginOwner()
        compose.onNodeWithTag("card-ventas").assertExists()
        compose.onNodeWithTag("card-fiado").assertExists()
        // Contrato v2 · tickets: «Pendientes» se reemplaza por «Cobrado hoy».
        compose.onNodeWithTag("card-cobrado").assertExists()
        compose.onNodeWithText("Cobrado hoy").assertExists()
        compose.onNodeWithText("efectivo + PEY").assertExists()
        compose.onNodeWithTag("card-stock").assertExists()
        compose.onNodeWithTag("card-pendientes").assertDoesNotExist()
        compose.onNodeWithText("Pendientes").assertDoesNotExist()
        compose.onNodeWithText("Cobros PEY por conciliar").assertDoesNotExist()
        compose.onNodeWithText("Fiado de clientes").assertDoesNotExist()
        compose.onNodeWithTag("abrir-ajustes").performClick()
        compose.onNodeWithText("Ajustes").assertExists()
        compose.onNodeWithText("Tu tienda").assertExists()
    }
}
