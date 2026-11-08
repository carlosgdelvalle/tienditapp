package mx.abarpay.mobile

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.test.core.app.ActivityScenario
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35], qualifiers = "w390dp-h844dp")
class AccessRecoveryUiTest {
    @get:Rule val compose = createEmptyComposeRule()
    private val prefs get() = RuntimeEnvironment.getApplication().getSharedPreferences("development_session", 0)

    @Test fun storedChargeAlwaysTakesPrecedenceOverLogin() {
        for (status in listOf("pending", "expired")) {
            val raw = saleJson(Sale("real-reference", 1800, 1, status = status)).toString()
            assertTrue(prefs.edit().clear().putString("sale", raw).commit())
            ActivityScenario.launch(MainActivity::class.java).use {
                compose.onNodeWithText("Cobro por revisar").assertIsDisplayed()
                compose.onNodeWithText("Iniciar sesión").assertDoesNotExist()
                assertEquals(raw, prefs.getString("sale", null))
            }
        }
    }

    @Test fun interruptedCreationCannotBeDismissedIntoMockLogin() {
        assertTrue(prefs.edit().clear().putBoolean("creating", true).commit())
        ActivityScenario.launch(MainActivity::class.java).use { scenario ->
            compose.onNodeWithText("Cobro por revisar").assertIsDisplayed()
            scenario.onActivity { it.onBackPressedDispatcher.onBackPressed() }
            compose.onNodeWithText("Cobro por revisar").assertIsDisplayed()
            compose.onNodeWithText("Iniciar sesión").assertDoesNotExist()
            assertTrue(prefs.getBoolean("creating", false))
        }
    }
}
