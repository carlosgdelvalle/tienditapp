package mx.abarpay.mobile

import android.app.Application
import androidx.compose.ui.test.*
import org.junit.Assert.assertFalse
import org.junit.Test

class OnboardingValidationUiTest : AppUiTest() {
    override fun startOnboarded() = false

    @Test fun onboardingCannotFinishUntilNameStoreAndTypeAreComplete() {
        waitReady()
        scrollToTag("onboarding-listo").assertIsNotEnabled()
        scrollToTag("onboarding-dueno").performTextInput("Rosa")
        scrollToTag("onboarding-negocio").performTextInput("La Esquina")
        scrollToTag("onboarding-listo").assertIsNotEnabled()
        scrollToTag("tipo-tiendita").performClick()
        scrollToTag("onboarding-listo").assertIsEnabled()
        val prefs = model().getApplication<Application>().getSharedPreferences("abarpay_owner", 0)
        assertFalse(prefs.getBoolean("onboarded_owner", false))
    }
}
