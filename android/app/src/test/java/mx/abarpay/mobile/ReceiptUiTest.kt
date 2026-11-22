package mx.abarpay.mobile

import androidx.compose.ui.test.*
import org.junit.Assert.*
import org.junit.Test

/** Contrato v3 · comprobante: en venta asentada, vista previa y compartir imagen/PDF. */
class ReceiptUiTest : AppUiTest() {
    @Test fun settledCashSaleOffersReceiptPreviewAndShareButtons() {
        loginOwner()
        compose.openDemoCheckout()
        compose.waitUntil(15_000) { !model().ui.value.busy }
        compose.onNodeWithContentDescription("Agregar Coca-Cola 600 ml").performScrollTo().performClick()
        compose.onNodeWithTag("abrir-pago").performClick()
        compose.onNodeWithTag("pago-efectivo").performClick()
        compose.onNodeWithTag("efectivo-recibido").performTextInput("100")
        compose.onNodeWithText("Cobrar en efectivo").performScrollTo().performClick()
        compose.waitUntil(15_000) { model().ui.value.sale?.settled == true && !model().ui.value.busy }

        scrollToTag("compartir-comprobante").performClick()
        compose.onNodeWithText("Comprobante de venta").assertExists()
        compose.onNodeWithTag("compartir-imagen").assertExists()
        compose.onNodeWithTag("compartir-pdf").assertExists()
        // La vista previa usa el negocio genérico del demo y el total de la venta.
        compose.onNodeWithText("Mi negocio").assertExists()
        compose.onAllNodesWithText("$18.00").fetchSemanticsNodes().let {
            org.junit.Assert.assertTrue("El comprobante debe mostrar el total", it.isNotEmpty())
        }
        compose.onNodeWithText("Cerrar").performClick()

        // Compartir imagen: ACTION_SEND con FileProvider (sin crash; el selector del
        // sistema no existe en Robolectric, así que la app puede avisar si falla).
        scrollToTag("compartir-comprobante").performClick()
        compose.onNodeWithTag("compartir-imagen").performClick()
        compose.waitForIdle()
        compose.onNodeWithText("Cerrar").assertDoesNotExist()
    }
}
