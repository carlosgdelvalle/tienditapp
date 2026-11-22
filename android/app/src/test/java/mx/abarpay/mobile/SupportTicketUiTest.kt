package mx.abarpay.mobile

import androidx.compose.ui.test.*
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Contrato v2 · tickets: un cobro PEY que quedó «por conciliar» (SIMULADO) ofrece
 * «Reportar problema» y la app confirma «Ticket #… creado».
 */
class SupportTicketUiTest : AppUiTest() {
    @Test fun porConciliarSaleLetsTheUserReportAProblem() {
        loginOwner()
        compose.openDemoCheckout()
        compose.waitUntil(15_000) { !model().ui.value.busy }
        compose.onNodeWithContentDescription("Agregar Coca-Cola 600 ml").performScrollTo().performClick()
        compose.onNodeWithTag("abrir-pago").performClick()
        compose.onNodeWithTag("pago-pey").performClick()
        compose.onNodeWithText("Generar QR PEY").performScrollTo().performClick()
        compose.waitUntil(15_000) { model().ui.value.sale?.status == "pending" && !model().ui.value.busy }

        // Con el cobro pendiente todavía no hay ticket: el botón aparece solo al conciliar.
        compose.onNodeWithTag("reportar-problema").assertDoesNotExist()

        // SIMULADO: deja la venta en «por_conciliar» sin red ni dinero.
        compose.runOnIdle { model().simulateUnconfirmed() }
        compose.waitUntil(15_000) {
            model().ui.value.sale?.status == "por_conciliar" && !model().ui.value.busy
        }

        scrollToTag("reportar-problema").performClick()
        compose.onNodeWithTag("ticket-nota").assertExists()
        compose.onNodeWithTag("ticket-nota").performTextInput("El cliente dice que ya pagó")
        compose.onNodeWithTag("crear-ticket").performClick()
        compose.waitUntil(15_000) { model().ui.value.supportTicket != null && !model().ui.value.busy }

        val ticket = model().ui.value.supportTicket!!
        assertTrue("El ticket debe traer folio del servidor", ticket.id.startsWith("tkt_"))
        assertEquals("El cliente dice que ya pagó", ticket.note)
        assertEquals("Ticket #" + ticket.id + " creado", model().ui.value.message)
        compose.onNodeWithText("Ticket #" + ticket.id + " creado").assertExists()
    }
}
