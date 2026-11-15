package mx.abarpay.mobile

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/**
 * Contrato v3 · «Tareas del día» (dueño, desde Inicio). Asigna cada tarea fija
 * del tipo de negocio a una persona y la activa o desactiva con PATCH /api/tasks.
 * El empleado solo ve las tareas que tiene asignadas.
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
internal fun TasksScreen(s: ShopState, vm: ShopViewModel) {
    val tasks = s.tasks.orEmpty()
    val employees = assignableEmployees(s.team)
    LazyColumn(contentPadding = PaddingValues(20.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        item {
            TextButton(onClick = vm::closeTasks, enabled = !s.busy) {
                Icon(Icons.AutoMirrored.Outlined.ArrowBack, null, Modifier.size(18.dp))
                Spacer(Modifier.width(8.dp))
                Text("Volver al inicio")
            }
        }
        item {
            Title("Tareas del día")
            MutedText("Asigna cada tarea a una persona. Las tareas sin asignar no aparecen en el teléfono del empleado.")
        }
        if (tasks.isEmpty()) {
            item { MutedText("Aún no hay tareas para este negocio. Se crean al aplicar la plantilla del tipo.") }
        }
        items(tasks, key = { "task-" + it.id }) { task ->
            Panel {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(task.title, Modifier.weight(1f), fontWeight = FontWeight.Bold, fontSize = 16.sp)
                    Switch(
                        checked = task.active,
                        onCheckedChange = { vm.setTaskActive(task.id, it) },
                        enabled = !s.busy,
                        modifier = Modifier.testTag("tarea-activa-" + task.id),
                    )
                }
                Text(
                    "Asignada a: " + taskAssigneeName(task, s.team),
                    color = Muted,
                    fontSize = 12.sp,
                )
                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    FilterChip(
                        selected = task.assignedEmployeeId == null,
                        onClick = { vm.assignTask(task.id, null) },
                        enabled = !s.busy,
                        label = { Text("Sin asignar") },
                        modifier = Modifier.testTag("tarea-sin-asignar-" + task.id),
                    )
                    employees.forEach { employee ->
                        FilterChip(
                            selected = task.assignedEmployeeId == employee.id,
                            onClick = { vm.assignTask(task.id, employee.id) },
                            enabled = !s.busy,
                            label = { Text(employee.displayName) },
                            modifier = Modifier.testTag("tarea-asignar-" + task.id + "-" + employee.id),
                        )
                    }
                }
            }
        }
    }
}
