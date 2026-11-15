package mx.abarpay.mobile

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import org.junit.Assert.assertEquals
import org.junit.Test

/** Contrato v3.2 · sin canFiado se ven saldo e historial, pero no los controles de abono. */
class FiadoAbonoGateUiTest : AppUiTest() {
    @Test fun employeeWithoutFiadoSeesBalanceAndHistoryWithoutControls() {
        waitReady()
        compose.runOnIdle {
            model().select(model().ui.value.bootstrap!!.employees.first { it.name == "Beto" })
        }
        compose.waitUntil(15_000) { model().ui.value.employee?.name == "Beto" && !model().ui.value.busy }
        compose.onNodeWithTag("tab-Fiado").performClick()
        compose.waitUntil(15_000) { model().ui.value.tab == TAB_FIADO && !model().ui.value.busy }
        compose.onNodeWithText("Doña Mari (ejemplo)").performClick()
        compose.waitUntil(15_000) { model().ui.value.customerDetail != null && !model().ui.value.busy }

        scrollToText("Saldo pendiente").assertIsDisplayed()
        scrollToText("Tu perfil no puede registrar abonos").assertIsDisplayed()
        compose.onNodeWithTag("abono-monto").assertDoesNotExist()
        compose.onNodeWithTag("abono-registrar").assertDoesNotExist()
        compose.onNodeWithTag("abono-liquidar").assertDoesNotExist()
        compose.onNodeWithTag("abono-preset-50").assertDoesNotExist()
        compose.onNodeWithText("Liquidar saldo").assertDoesNotExist()
        compose.onNodeWithText("Registrar abono").assertDoesNotExist()

        // El historial sí se lee (el detalle del cliente ya lo trae).
        scrollToText("Historial").assertIsDisplayed()
        val history = model().ui.value.fiadoEntries
        assertEquals(1, history.size)
        assertEquals("charge", history.first().kind)
        assertEquals(3_500L, history.first().amountCents)
    }
}
