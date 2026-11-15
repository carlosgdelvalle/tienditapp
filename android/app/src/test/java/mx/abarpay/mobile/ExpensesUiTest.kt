package mx.abarpay.mobile

import androidx.compose.ui.test.*
import org.junit.Assert.*
import org.junit.Test

/** Contrato v3 · gastos: botón en Inicio, diálogo monto+nota, dictado y reportes. */
class ExpensesUiTest : AppUiTest() {
    @Test fun ownerRegistersAnExpenseAndReportsShowsIt() {
        loginOwner()
        scrollToTag("registrar-gasto")
        compose.onNodeWithTag("registrar-gasto").performClick()
        compose.onNodeWithTag("gasto-monto").assertExists()
        compose.onNodeWithTag("gasto-voz").assertExists()
        compose.onNodeWithTag("gasto-monto").performTextInput("20")
        compose.onNodeWithTag("gasto-nota").performTextInput("gas")
        compose.onNodeWithTag("gasto-guardar").performClick()
        compose.waitUntil(15_000) {
            !model().ui.value.busy && model().ui.value.report?.totalExpensesCents == 2000L
        }
        assertEquals("Gasto registrado: $20.00 · gas", model().ui.value.message)
        compose.onNodeWithTag("tab-Reportes").performClick()
        compose.waitUntil(15_000) { !model().ui.value.busy && model().ui.value.report != null }
        scrollToText("Gastos de hoy")
        compose.onNodeWithText("$20.00").assertExists()
    }

    @Test fun employeeSeesTheExpenseButtonAndVoiceDraft() {
        waitReady()
        compose.runOnIdle { model().select(model().ui.value.bootstrap!!.employees.first { it.id == 2 }) }
        compose.waitUntil(15_000) { model().ui.value.employee?.id == 2 && !model().ui.value.busy }
        compose.onNodeWithTag("registrar-gasto").assertExists()
        // El dictado solo propone el gasto: nada se guarda hasta confirmar.
        compose.runOnIdle { model().expenseVoice("veinte pesos de gas") }
        compose.waitUntil(15_000) { !model().ui.value.busy && model().ui.value.expenseDraft?.amountCents == 2000L }
        assertEquals("Entendí: $20.00 · gas", model().ui.value.message)
        compose.onNodeWithTag("registrar-gasto").performClick()
        compose.onNodeWithTag("gasto-monto").assertExists()
        compose.onNodeWithTag("gasto-nota").assertExists()
        compose.onNodeWithTag("gasto-guardar").performClick()
        compose.waitUntil(15_000) { !model().ui.value.busy && model().ui.value.message == "Gasto registrado: $20.00 · gas" }
    }
}
