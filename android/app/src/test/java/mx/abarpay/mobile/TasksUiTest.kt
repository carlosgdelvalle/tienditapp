package mx.abarpay.mobile

import androidx.compose.ui.test.*
import org.junit.Assert.*
import org.junit.Test

/** Contrato v3 · tareas del día: el dueño asigna y el empleado SOLO ve las suyas. */
class TasksUiTest : AppUiTest() {
    @Test fun ownerAssignsTasksAndEmployeeOnlySeesAssignedOnes() {
        loginOwner()
        scrollToTag("abrir-tareas")
        compose.onNodeWithTag("abrir-tareas").performClick()
        compose.waitUntil(15_000) { model().ui.value.tasksOpen && !model().ui.value.busy }
        compose.onNodeWithText("Tareas del día").assertExists()

        val all = model().ui.value.tasks.orEmpty()
        assertTrue("El dueño ve también las tareas sin asignar", all.any { it.assignedEmployeeId == null })
        assertTrue("El dueño ve tareas asignadas a otros", all.any { it.assignedEmployeeId == 3 })

        // Asigna «Limpiar tienda» a Lupita (id 2) con PATCH /api/tasks/{id}.
        compose.onNodeWithTag("tarea-asignar-2-2").performScrollTo().performClick()
        compose.waitUntil(15_000) {
            !model().ui.value.busy && model().ui.value.tasks?.firstOrNull { it.id == 2 }?.assignedEmployeeId == 2
        }

        // El empleado solo ve sus tareas asignadas y activas.
        compose.runOnIdle { model().select(model().ui.value.bootstrap!!.employees.first { it.id == 2 }) }
        compose.waitUntil(15_000) { model().ui.value.employee?.id == 2 && !model().ui.value.busy }
        compose.onNodeWithText("Tareas del negocio").assertExists()
        compose.onNodeWithText("Contar inventario").assertExists()
        compose.onNodeWithText("Limpiar tienda").assertExists()
        compose.onNodeWithText("Revisar fechas de caducidad").assertDoesNotExist()
        compose.onNodeWithText("Acomodar anaquel").assertDoesNotExist()
        val visible = tasksFor(model().ui.value.tasks, model().ui.value.employee)
        assertTrue(visible.isNotEmpty())
        assertTrue(visible.all { it.assignedEmployeeId == 2 && it.active })
    }

    @Test fun ownerCanDeactivateATaskAndItDisappearsForTheEmployee() {
        loginOwner()
        scrollToTag("abrir-tareas")
        compose.onNodeWithTag("abrir-tareas").performClick()
        compose.waitUntil(15_000) { model().ui.value.tasksOpen && !model().ui.value.busy }
        compose.onNodeWithTag("tarea-activa-1").performScrollTo().performClick()
        compose.waitUntil(15_000) {
            !model().ui.value.busy && model().ui.value.tasks?.firstOrNull { it.id == 1 }?.active == false
        }
        compose.runOnIdle { model().select(model().ui.value.bootstrap!!.employees.first { it.id == 2 }) }
        compose.waitUntil(15_000) { model().ui.value.employee?.id == 2 && !model().ui.value.busy }
        compose.onNodeWithText("Contar inventario").assertDoesNotExist()
        compose.onNodeWithText("No tienes tareas asignadas para hoy. El dueño puede asignarte desde su teléfono.").assertExists()
    }
}
