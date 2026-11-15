package mx.abarpay.mobile

import android.content.Intent
import android.content.SharedPreferences
import android.net.Uri
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.test.core.app.ActivityScenario
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35], qualifiers = "w390dp-h844dp")
@GraphicsMode(GraphicsMode.Mode.NATIVE)
class InviteHttpsUiTest {
    @get:Rule val compose = createEmptyComposeRule()

    @Test fun httpsInviteLinkOpensTheSameAcceptanceScreen() {
        val app = RuntimeEnvironment.getApplication()
        app.getSharedPreferences("development_session", 0).edit().clear().commit()
        app.getSharedPreferences("abarpay_owner", 0).edit().clear().commit()
        val intent = Intent(Intent.ACTION_VIEW, Uri.parse("https://abarpay-api.onrender.com/invite/INVITACION-DEMO"))
        ActivityScenario.launch<MainActivity>(intent).use { scenario ->
            var ownerPrefs: SharedPreferences? = null
            scenario.onActivity { activity ->
                ownerPrefs = activity.application.getSharedPreferences("abarpay_owner", 0)
            }
            val prefs = ownerPrefs!!
            compose.waitUntil(15_000) { compose.onAllNodesWithText("Ponle tu apodo").fetchSemanticsNodes().isNotEmpty() }
            compose.onNodeWithTag("aceptar-invitacion").assertExists()
            compose.onNodeWithTag("invite-nickname").assertExists()
        }
    }
}
