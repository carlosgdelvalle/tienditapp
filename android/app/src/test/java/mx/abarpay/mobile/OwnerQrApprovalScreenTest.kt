package mx.abarpay.mobile

import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTextInput
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35])
@GraphicsMode(GraphicsMode.Mode.NATIVE)
class OwnerQrApprovalScreenTest {

    @get:Rule
    val compose = createComposeRule()

    @Test
    fun firstRunShowsPhoneAndThenSmsCode() {
        var sentTo: String? = null
        val fakeAuth = object : OwnerAuth {
            override suspend fun accessToken(): String? = null
            override suspend fun startEnrollment(phone: String, inviteToken: String?): String {
                sentTo = phone
                return "synthetic-challenge"
            }
            override suspend fun verifyEnrollment(challengeId: String, code: String) = Unit
        }
        compose.setContent {
            OwnerQrApprovalScreen(fakeAuth, "https://owner.example.test", onClose = {})
        }

        compose.onNodeWithTag("owner-start").performClick()
        compose.onNodeWithTag("owner-phone").performTextInput("5512345678")
        compose.onNodeWithTag("owner-send-code").performClick()
        compose.onNodeWithTag("owner-code").assertExists()
        assertEquals("5512345678", sentTo)
    }
}
