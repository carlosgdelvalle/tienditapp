package mx.abarpay.mobile

import androidx.compose.ui.test.*
import org.junit.Test

class FiadoChipUiTest : AppUiTest() {
    @Test fun employeeWithoutFiadoSeesTheChipDisabled() {
        waitReady()
        compose.runOnIdle {
            model().select(model().ui.value.bootstrap!!.employees.first { it.name == "Beto" })
        }
        compose.waitUntil(15_000) { model().ui.value.employee?.name == "Beto" && !model().ui.value.busy }
        compose.openDemoCheckout()
        compose.waitUntil(15_000) { !model().ui.value.busy }
        compose.onNodeWithContentDescription("Agregar Coca-Cola 600 ml").performScrollTo().performClick()
        compose.onNodeWithTag("abrir-pago").performClick()
        compose.onNodeWithTag("pago-fiado").assertIsNotEnabled()
        compose.onNodeWithTag("pago-efectivo").assertIsEnabled()
    }
}
