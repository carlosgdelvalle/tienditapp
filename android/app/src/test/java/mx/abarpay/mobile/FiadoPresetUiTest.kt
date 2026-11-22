package mx.abarpay.mobile

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertTextContains
import androidx.compose.ui.test.hasScrollToIndexAction
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performScrollToKey
import org.junit.Assert.assertEquals
import org.junit.Test

/** Contrato v3.2 · preset «Abonar $50» cuando el saldo lo permite; $100 se oculta. */
class FiadoPresetUiTest : AppUiTest() {
    @Test fun ownerUsesTheRoundedPresetAndTheHistoryReloads() {
        loginOwner()
        // Deja un saldo de $53: cargo del ejemplo ($35) + venta a fiado ($18).
        compose.openDemoCheckout()
        compose.waitUntil(15_000) { model().ui.value.tab == TAB_SELL && !model().ui.value.busy }
        compose.onNode(hasScrollToIndexAction()).performScrollToKey("product-1")
        addProduct()
        compose.onNodeWithTag("abrir-pago").performClick()
        compose.onNodeWithTag("pago-fiado").performClick()
        compose.onNodeWithText("Doña Mari (ejemplo) · $35.00").performScrollTo().performClick()
        compose.onNodeWithText("Cobrar a fiado").performScrollTo().performClick()
        scrollToText("Nuevo cobro").performClick()
        compose.waitUntil(15_000) { model().ui.value.sale == null && !model().ui.value.busy }

        compose.onNodeWithTag("tab-Fiado").performClick()
        compose.waitUntil(15_000) { model().ui.value.tab == TAB_FIADO && !model().ui.value.busy }
        compose.onNodeWithText("Doña Mari (ejemplo)").performClick()
        compose.waitUntil(15_000) {
            model().ui.value.customerDetail?.customer?.balanceCents == 5_300L && !model().ui.value.busy
        }

        // Solo el preset que cabe en el saldo.
        scrollToTag("abono-preset-50").assertIsDisplayed()
        compose.onNodeWithTag("abono-preset-100").assertDoesNotExist()
        scrollToTag("abono-preset-50").performClick()
        compose.onNodeWithTag("abono-monto").performScrollTo().assertTextContains("50")

        scrollToTag("abono-registrar").performClick()
        compose.waitUntil(15_000) {
            model().ui.value.customerDetail?.customer?.balanceCents == 300L && !model().ui.value.busy
        }
        compose.onNodeWithText("Abono registrado. Saldo: $3.00.").assertIsDisplayed()

        val history = model().ui.value.fiadoEntries
        assertEquals(3, history.size) // cargo de ejemplo + venta + abono
        assertEquals("payment", history.first().kind)
        assertEquals(5_000L, history.first().amountCents)
        scrollToText("−" + money(5_000)).assertIsDisplayed()

        // Con $3 pendientes, el preset de $50 deja de tener sentido.
        scrollToText("Liquidar saldo").assertIsDisplayed()
        compose.onNodeWithTag("abono-preset-50").assertDoesNotExist()
    }
}
