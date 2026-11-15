package mx.abarpay.mobile

import androidx.compose.ui.test.*
import org.junit.Test

class EmployeePermissionsUiTest : AppUiTest() {
    @Test fun employeeTasksAndTabsFollowPermissions() {
        waitReady()
        compose.runOnIdle {
            model().select(model().ui.value.bootstrap!!.employees.first { it.name == "Toño" })
        }
        compose.waitUntil(15_000) { model().ui.value.employee?.name == "Toño" && !model().ui.value.busy }
        compose.onNodeWithText("Tus tareas de hoy").assertExists()
        compose.onNodeWithText("Hola, Toño").assertExists()
        compose.onNodeWithTag("tab-Inicio").assertExists()
        compose.onNodeWithTag("tab-Fiado").assertExists()
        compose.onNodeWithTag("tab-Cobrar").assertDoesNotExist()
        compose.onNodeWithTag("tab-Inventario").assertDoesNotExist()
        compose.onNodeWithTag("tab-Reportes").assertDoesNotExist()
    }
}
