package mx.abarpay.mobile

import android.app.Application
import androidx.compose.ui.test.*
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class OnboardingFirstLaunchUiTest : AppUiTest() {
    override fun startOnboarded() = false

    @Test fun firstLaunchCompletesOwnerOnboardingAndSavesPreferences() {
        waitReady()
        compose.onNodeWithText("Bienvenido a Abarpay").assertExists()
        compose.onNodeWithText("¿Qué quieres lograr?").assertExists()
        scrollToTag("meta-0").performClick()
        scrollToTag("meta-2").performClick()
        scrollToTag("onboarding-dueno").performTextInput("Doña Rosa")
        scrollToTag("onboarding-negocio").performTextInput("Tiendita de la Esquina")
        scrollToTag("tipo-tiendita").performClick()
        scrollToTag("onboarding-listo").assertIsEnabled()
        scrollToTag("onboarding-listo").performClick()
        compose.waitUntil(15_000) { model().ui.value.onboarded && !model().ui.value.busy }
        // El ViewModel usa la aplicación de esta prueba: aquí sí se comprueba la persistencia.
        val prefs = model().getApplication<Application>().getSharedPreferences("abarpay_owner", 0)
        assertTrue(prefs.getBoolean("onboarded_owner", false))
        assertEquals(
            "Organizar mis ventas y gastos|Gestionar mejor mi inventario",
            prefs.getString("owner_goals", null),
        )
        assertEquals("Tiendita de la Esquina", model().ui.value.bootstrap?.store?.name)
        scrollToText("Entrar en simulación")
        compose.onNodeWithText("Entrar en simulación").assertExists()
    }
}
