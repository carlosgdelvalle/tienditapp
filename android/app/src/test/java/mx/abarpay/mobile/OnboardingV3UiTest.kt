package mx.abarpay.mobile

import android.app.Application
import androidx.compose.ui.test.*
import org.junit.Assert.*
import org.junit.Test

/** Contrato v3 · onboarding ampliado: tipos, «¿Qué vendes?», metas con Omitir y plantilla. */
class OnboardingV3UiTest : AppUiTest() {
    override fun startOnboarded() = false

    @Test fun onboardingV3ShowsAllTypesSellsAndOmitirThenAppliesTemplate() {
        waitReady()
        // Lista ampliada de tipos de negocio.
        listOf(
            "tipo-tiendita", "tipo-miscelanea", "tipo-tortilleria", "tipo-taqueria",
            "tipo-comida-corrida", "tipo-peluqueria", "tipo-estetica", "tipo-fondita", "tipo-otro",
        ).forEach { scrollToTag(it).assertExists() }
        scrollToText("¿Qué vendes?").assertExists()
        scrollToTag("vende-productos").assertExists()
        scrollToTag("vende-servicios").assertExists()
        scrollToTag("vende-comida").assertExists()

        // Las metas se pueden omitir.
        scrollToTag("meta-0").performClick()
        scrollToTag("metas-omitir").performClick()
        scrollToTag("onboarding-dueno").performTextInput("Doña Rosa")
        scrollToTag("onboarding-negocio").performTextInput("Mi negocio")
        scrollToTag("tipo-taqueria").performClick()
        scrollToTag("vende-productos").performClick()
        scrollToTag("vende-comida").performClick()
        scrollToTag("onboarding-listo").performClick()
        compose.waitUntil(15_000) { model().ui.value.onboarded && !model().ui.value.busy }

        val prefs = model().getApplication<Application>().getSharedPreferences("abarpay_owner", 0)
        assertTrue(prefs.getBoolean("onboarded_owner", false))
        assertEquals("", prefs.getString("owner_goals", null))
        assertEquals("Productos|Comida preparada y bebidas", prefs.getString("owner_sells", null))
        assertEquals("Taquería", model().ui.value.bootstrap?.store?.businessType)
        // El demo reproduce la plantilla y las tareas del tipo elegido.
        assertTrue(
            "La plantilla de taquería debe traer tacos",
            model().ui.value.bootstrap!!.products.any { it.name.contains("Taco") },
        )
        assertTrue(model().ui.value.tasks.orEmpty().isNotEmpty())
    }
}
