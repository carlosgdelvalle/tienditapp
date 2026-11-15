package mx.abarpay.mobile

import androidx.compose.ui.test.*
import org.junit.Assert.assertEquals
import org.junit.Test

class VoiceInventoryUiTest : AppUiTest() {
    @Test fun voiceCountConfirmationUpdatesStock() {
        loginOwner()
        compose.onNodeWithTag("tab-Inventario").performClick()
        compose.waitUntil(15_000) { !model().ui.value.busy }
        compose.runOnIdle { model().voiceInventory("12 coca colas") }
        compose.waitUntil(15_000) { model().ui.value.voice != null && !model().ui.value.busy }
        compose.onNodeWithText("Confirma tu conteo").assertExists()
        compose.onNodeWithTag("voice-qty-1").assertExists()
        compose.onNodeWithTag("voice-guardar").performClick()
        compose.waitUntil(15_000) { model().ui.value.voice == null && !model().ui.value.busy }
        scrollToText("Stock: 12 pza")
        compose.onNodeWithText("Stock: 12 pza").assertExists()
        assertEquals(12000, model().ui.value.bootstrap?.products?.first { it.id == 1 }?.stockMilli)
    }
}
