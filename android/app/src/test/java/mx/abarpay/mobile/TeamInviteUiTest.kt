package mx.abarpay.mobile

import androidx.compose.ui.test.*
import org.junit.Assert.assertTrue
import org.junit.Test

class TeamInviteUiTest : AppUiTest() {
    @Test fun ownerInvitesEmployeeWithQrAndPermissionSwitches() {
        loginOwner()
        scrollToTag("abrir-equipo")
        compose.onNodeWithTag("abrir-equipo").performClick()
        compose.waitUntil(15_000) { model().ui.value.teamOpen && !model().ui.value.busy }
        compose.onNodeWithText("Equipo").assertExists()
        scrollToTag("perm-2-fiado")
        compose.onNodeWithTag("perm-2-fiado").performClick()
        compose.waitUntil(15_000) { model().ui.value.team?.firstOrNull { it.id == 2 }?.canFiado == false }
        scrollToTag("invitar-empleado")
        compose.onNodeWithTag("invitar-empleado").performClick()
        scrollToTag("invite-name")
        compose.onNodeWithTag("invite-name").performTextInput("Juan")
        scrollToTag("invite-canInventory")
        compose.onNodeWithTag("invite-canInventory").performClick()
        scrollToTag("crear-invitacion")
        compose.onNodeWithTag("crear-invitacion").performClick()
        compose.waitUntil(15_000) { model().ui.value.invite != null && !model().ui.value.busy }
        compose.waitUntil(15_000) {
            compose.onAllNodesWithContentDescription("QR de la invitación").fetchSemanticsNodes().isNotEmpty()
        }
        compose.onNodeWithTag("invite-url").assertExists()
        compose.onNodeWithContentDescription("QR de la invitación").assertExists()
        val invite = model().ui.value.invite!!
        assertTrue(invite.url.contains(invite.token))
        assertTrue(model().ui.value.team?.any { it.name == "Juan" && !it.active } == true)
    }
}
