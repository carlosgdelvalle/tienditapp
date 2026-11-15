package mx.abarpay.mobile

import android.app.Activity
import android.content.ActivityNotFoundException
import android.content.Intent
import android.speech.RecognizerIntent
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Mic
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Icon
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp

/**
 * Contrato v3 · «Registrar gasto»: monto + nota + micrófono. El dictado solo
 * propone el monto y la nota (POST /api/expenses/voice); nada se guarda hasta
 * que la persona confirma y la app manda POST /api/expenses.
 */
@Composable
internal fun RegisterExpenseDialog(
    busy: Boolean,
    draft: ExpenseDraft?,
    onVoice: (String) -> Unit,
    onDismiss: () -> Unit,
    onSave: (Long, String?) -> Unit,
) {
    var amount by rememberSaveable {
        mutableStateOf(draft?.let { if (it.amountCents > 0) cashInputText(it.amountCents) else "" } ?: "")
    }
    var note by rememberSaveable { mutableStateOf(draft?.note.orEmpty()) }
    LaunchedEffect(draft) {
        if (draft != null) {
            if (draft.amountCents > 0) amount = cashInputText(draft.amountCents)
            draft.note?.takeIf { it.isNotBlank() }?.let { note = it }
        }
    }
    val voice = rememberLauncherForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
        val spoken = result.data?.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS)?.firstOrNull()
        if (result.resultCode == Activity.RESULT_OK && !spoken.isNullOrBlank()) onVoice(spoken)
    }
    fun dictate() {
        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, "es-MX")
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_PREFERENCE, "es-MX")
            putExtra(RecognizerIntent.EXTRA_PROMPT, "Dicta el gasto: veinte pesos de gas")
        }
        try {
            voice.launch(intent)
        } catch (_: ActivityNotFoundException) {
            // Sin reconocimiento de voz: el monto y la nota se escriben a mano.
        }
    }
    val cents = parseCashCents(amount)
    AlertDialog(
        onDismissRequest = { if (!busy) onDismiss() },
        title = { Text("Registrar gasto") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                MutedText("Monto y nota. Nada se guarda hasta que confirmes.", 12)
                // Ancho fijo: fillMaxWidth dentro de un diálogo dispara un ciclo de
                // medida en Robolectric y las pruebas Compose nunca quedan ociosas.
                OutlinedTextField(
                    amount, { amount = it },
                    Modifier.width(220.dp).testTag("gasto-monto"),
                    label = { Text("Monto (MXN)") },
                    singleLine = true,
                    enabled = !busy,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                    shape = RoundedCornerShape(16.dp),
                )
                OutlinedTextField(
                    note, { note = it },
                    Modifier.width(240.dp).testTag("gasto-nota"),
                    label = { Text("Nota (opcional)") },
                    singleLine = true,
                    enabled = !busy,
                    shape = RoundedCornerShape(16.dp),
                )
                OutlinedButton(
                    onClick = { dictate() },
                    enabled = !busy,
                    modifier = Modifier.fillMaxWidth().testTag("gasto-voz"),
                ) {
                    Icon(Icons.Outlined.Mic, null, Modifier.size(18.dp))
                    Spacer(Modifier.width(8.dp))
                    Text("Dictar gasto")
                }
                draft?.takeIf { it.amountCents > 0 }?.let {
                    Row { MutedText(expenseVoiceMessage(it), 12) }
                }
            }
        },
        confirmButton = {
            TextButton(
                onClick = {
                    cents?.takeIf { it > 0 }?.let { onSave(it, note.trim().ifBlank { null }) }
                },
                enabled = cents != null && cents > 0 && !busy,
                modifier = Modifier.testTag("gasto-guardar"),
            ) { Text("Guardar gasto") }
        },
        dismissButton = { TextButton(onClick = onDismiss, enabled = !busy) { Text("Cancelar") } },
    )
}
