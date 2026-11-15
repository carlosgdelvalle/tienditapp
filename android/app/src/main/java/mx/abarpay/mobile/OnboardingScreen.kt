package mx.abarpay.mobile

import android.Manifest
import android.content.pm.PackageManager
import android.graphics.Bitmap
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.PhotoCamera
import androidx.compose.material3.Button
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat

/**
 * Onboarding solo para el dueño en el primer arranque. Las metas viven en las
 * preferencias del teléfono; el perfil y la foto van al servidor.
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
internal fun OnboardingScreen(s: ShopState, vm: ShopViewModel) {
    var goalsText by rememberSaveable { mutableStateOf("") }
    var ownerName by rememberSaveable { mutableStateOf("") }
    var storeName by rememberSaveable { mutableStateOf("") }
    var businessType by rememberSaveable { mutableStateOf("") }
    var photo by remember { mutableStateOf<Bitmap?>(null) }
    val context = LocalContext.current
    val selectedGoals = goalsText.split("|").map { it.trim() }.filter { it.isNotBlank() }

    val camera = rememberLauncherForActivityResult(ActivityResultContracts.TakePicturePreview()) { bitmap ->
        if (bitmap != null) photo = bitmap
    }
    val permission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (granted) runCatching { camera.launch(null) }
    }
    fun takePhoto() {
        val granted = ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) ==
            PackageManager.PERMISSION_GRANTED
        if (granted) {
            runCatching { camera.launch(null) }.onFailure {
                vm.message("No pudimos abrir la cámara. Puedes continuar sin foto.")
            }
        } else {
            permission.launch(Manifest.permission.CAMERA)
        }
    }
    fun toggleGoal(goal: String) {
        val next = if (goal in selectedGoals) selectedGoals - goal else selectedGoals + goal
        goalsText = next.joinToString("|")
    }

    val ready = onboardingReady(ownerName, storeName, businessType) && !s.busy
    LazyColumn(contentPadding = PaddingValues(20.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        item {
            Text("Bienvenido a Abarpay", fontSize = 27.sp, fontWeight = FontWeight.Bold)
            MutedText("Configura tu tienda en un minuto. Este paso es solo para el dueño y no se repite.")
        }
        item {
            SectionLabel("¿Qué quieres lograr?")
            MutedText("Elige todas las metas que quieras. Se guardan solo en este teléfono.")
        }
        items(OWNER_GOALS.size) { index ->
            val goal = OWNER_GOALS[index]
            FilterChip(
                selected = goal in selectedGoals,
                onClick = { toggleGoal(goal) },
                enabled = !s.busy,
                label = { Text(goal) },
                modifier = Modifier.fillMaxWidth().testTag("meta-" + index),
            )
        }
        item {
            SectionLabel("Sobre ti")
            OutlinedTextField(
                ownerName, { ownerName = it },
                Modifier.fillMaxWidth().testTag("onboarding-dueno"),
                label = { Text("Tu nombre (dueño)") },
                singleLine = true,
                enabled = !s.busy,
                shape = RoundedCornerShape(16.dp),
            )
        }
        item {
            SectionLabel("Tu negocio")
            OutlinedTextField(
                storeName, { storeName = it },
                Modifier.fillMaxWidth().testTag("onboarding-negocio"),
                label = { Text("Nombre de la tienda") },
                singleLine = true,
                enabled = !s.busy,
                shape = RoundedCornerShape(16.dp),
            )
        }
        item {
            Text("Tipo de negocio", fontWeight = FontWeight.SemiBold)
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                BUSINESS_TYPES.forEach { type ->
                    FilterChip(
                        selected = businessType == type,
                        onClick = { businessType = type },
                        enabled = !s.busy,
                        label = { Text(type) },
                        modifier = Modifier.testTag("tipo-" + type),
                    )
                }
            }
        }
        item {
            SectionLabel("Foto de tu negocio")
            MutedText("Opcional. Se sube a tu servidor y se muestra en la consola del dueño.")
            photo?.let { bitmap ->
                Image(
                    bitmap.asImageBitmap(),
                    "Foto de tu negocio",
                    Modifier.fillMaxWidth().height(170.dp).padding(top = 6.dp),
                    contentScale = ContentScale.Crop,
                )
            }
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                OutlinedButton(
                    onClick = { takePhoto() },
                    enabled = !s.busy,
                    modifier = Modifier.testTag("onboarding-foto"),
                ) {
                    Icon(Icons.Outlined.PhotoCamera, null, Modifier.size(18.dp))
                    Spacer(Modifier.width(8.dp))
                    Text(if (photo == null) "Tomar foto" else "Cambiar foto")
                }
                if (photo != null) {
                    TextButton(onClick = { photo = null }, enabled = !s.busy) { Text("Quitar") }
                }
            }
        }
        item {
            Button(
                onClick = { vm.finishOnboarding(selectedGoals, ownerName, storeName, businessType, photo) },
                enabled = ready,
                modifier = Modifier.fillMaxWidth().heightIn(min = 56.dp).testTag("onboarding-listo"),
                shape = RoundedCornerShape(16.dp),
            ) { Text("Empezar", fontSize = 17.sp) }
            if (!ready) {
                MutedText("Escribe el nombre del dueño, el de tu tienda y elige el tipo de negocio.", 12)
            }
        }
    }
}
