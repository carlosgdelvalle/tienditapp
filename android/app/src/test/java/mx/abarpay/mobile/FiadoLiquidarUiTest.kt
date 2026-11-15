package mx.abarpay.mobile

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertTextContains
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import org.junit.Assert.assertEquals
import org.junit.Test

/** Contrato v3.2 · «Liquidar saldo» llena el monto completo y refresca el historial. */
class FiadoLiquidarUiTest : AppUiTest() {
    @Test fun ownerLiquidatesTheWholeBalanceAndSeesTheHistory() {
        loginOwner()
        compose.onNodeWithTag("tab-Fiado").performClick()
        compose.waitUntil(15_000) { model().ui.value.tab == TAB_FIADO && !model().ui.value.busy }
        compose.onNodeWithText("Doña Mari (ejemplo)").performClick()
        compose.waitUntil(15_000) { model().ui.value.customerDetail != null && !model().ui.value.busy }

        scrollToText("Saldo pendiente").assertIsDisplayed()
        assertEquals(3_500L, model().ui.value.customerDetail!!.customer.balanceCents)
        // El saldo de $35 no alcanza para presets redondeados: solo se ofrece liquidar.
        scrollToTag("abono-liquidar").assertIsDisplayed()
        compose.onNodeWithTag("abono-preset-50").assertDoesNotExist()
        compose.onNodeWithTag("abono-preset-100").assertDoesNotExist()

        // El atajo escribe el saldo completo en el campo existente.
        scrollToTag("abono-liquidar").performClick()
        compose.onNodeWithTag("abono-monto").performScrollTo().assertTextContains("35")

        scrollToTag("abono-registrar").performClick()
        compose.waitUntil(15_000) {
            model().ui.value.customerDetail?.customer?.balanceCents == 0L && !model().ui.value.busy
        }
        compose.onNodeWithText("Abono registrado. Saldo: $0.00.").assertIsDisplayed()

        // Historial: recarga al abonar, con el empleado y el monto con signo.
        val history = model().ui.value.fiadoEntries
        assertEquals(2, history.size)
        assertEquals("payment", history.first().kind)
        assertEquals(3_500L, history.first().amountCents)
        assertEquals("Doña Rosa", history.first().employeeName)
        scrollToText("Historial").assertIsDisplayed()
        scrollToText("−" + money(3_500)).assertIsDisplayed()
        // Sin saldo ya no se ofrece liquidar.
        compose.onNodeWithTag("abono-liquidar").assertDoesNotExist()
    }
}
