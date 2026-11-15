package mx.abarpay.mobile

import androidx.compose.ui.test.SemanticsNodeInteraction
import androidx.compose.ui.test.hasScrollToIndexAction
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollToNode
import androidx.lifecycle.ViewModelProvider
import org.junit.Rule
import org.junit.rules.ExternalResource
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode

/**
 * Base de los flujos Compose. Cada escenario vive en su propia clase: así cada
 * prueba arranca con una aplicación y una actividad nuevas (Robolectric conserva
 * la actividad anterior entre métodos de una misma clase).
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35], qualifiers = "w390dp-h844dp")
@GraphicsMode(GraphicsMode.Mode.NATIVE)
abstract class AppUiTest {
    /** Los flujos de tienda arrancan con el onboarding del dueño ya hecho. */
    protected open fun startOnboarded(): Boolean = true

    @get:Rule(order = 0) val cleanSession = object : ExternalResource() {
        override fun before() {
            val app = RuntimeEnvironment.getApplication()
            app.getSharedPreferences("development_session", 0).edit().clear().commit()
            app.getSharedPreferences("abarpay_owner", 0).edit().clear()
                .putBoolean("onboarded_owner", startOnboarded())
                .commit()
        }
    }

    @get:Rule(order = 1) val compose = createAndroidComposeRule<MainActivity>()

    protected fun model(): ShopViewModel =
        ViewModelProvider(compose.activity)[ShopViewModel::class.java]

    protected fun waitReady() {
        compose.waitUntil(15_000) { model().ui.value.bootstrap != null && !model().ui.value.busy }
    }

    protected fun scrollToText(text: String): SemanticsNodeInteraction {
        compose.onNode(hasScrollToIndexAction()).performScrollToNode(hasText(text))
        return compose.onNodeWithText(text)
    }

    protected fun scrollToTag(tag: String): SemanticsNodeInteraction {
        compose.onNode(hasScrollToIndexAction()).performScrollToNode(hasTestTag(tag))
        return compose.onNodeWithTag(tag)
    }

    protected fun loginOwner() {
        waitReady()
        scrollToText("Entrar en simulación")
        compose.onNodeWithText("Entrar en simulación").performClick()
        compose.waitUntil(15_000) { model().ui.value.employee != null && !model().ui.value.busy }
    }
}
