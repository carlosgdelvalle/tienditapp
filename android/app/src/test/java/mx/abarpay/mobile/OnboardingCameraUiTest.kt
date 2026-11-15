package mx.abarpay.mobile

import androidx.compose.ui.test.*
import org.junit.Test

class OnboardingCameraUiTest : AppUiTest() {
    override fun startOnboarded() = false

    @Test fun cameraButtonIsAvailableForTheStorePhoto() {
        waitReady()
        scrollToText("Tomar foto")
        compose.onNodeWithTag("onboarding-foto").assertExists()
        compose.onNodeWithText("Tomar foto").assertExists()
        compose.onNodeWithText("Quitar").assertDoesNotExist()
    }
}
