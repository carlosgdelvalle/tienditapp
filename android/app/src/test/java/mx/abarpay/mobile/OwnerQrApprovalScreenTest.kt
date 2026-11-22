package mx.abarpay.mobile

import android.content.Intent
import android.net.Uri
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
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
    fun firstRunCtaReachesOidc() {
        var beginSignInCalls = 0
        val fakeAuth = object : OwnerAuth {
            override fun beginSignIn(): Intent {
                beginSignInCalls += 1
                return Intent(Intent.ACTION_VIEW)
            }
            override suspend fun completeSignIn(callback: Uri): String = "synthetic-token"
            override fun accessToken(): String? = null
            override fun clearAccessToken() {}
        }

        compose.setContent {
            OwnerQrApprovalScreen(
                ownerAuth = fakeAuth,
                apiBaseUrl = "https://owner.example.test",
                authRevision = 0,
                authError = null,
                onApproved = {},
                onClose = {},
            )
        }

        compose.onNodeWithTag("owner-start").performClick()
        assertEquals(1, beginSignInCalls)
    }
}
