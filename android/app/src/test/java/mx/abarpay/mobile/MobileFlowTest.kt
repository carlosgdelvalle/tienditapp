package mx.abarpay.mobile

import android.graphics.Bitmap
import android.graphics.Canvas
import java.io.File
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35], qualifiers = "w390dp-h844dp")
@GraphicsMode(GraphicsMode.Mode.NATIVE)
class MobileFlowTest {
    @get:Rule val compose = createAndroidComposeRule<MainActivity>()

    private fun scrollToText(text: String): SemanticsNodeInteraction {
        compose.onNode(hasScrollToIndexAction()).performScrollToNode(hasText(text))
        return compose.onNodeWithText(text)
    }
    private fun screenshot(name: String) {
        val decor = compose.activity.window.decorView
        val bitmap = Bitmap.createBitmap(decor.width, decor.height, Bitmap.Config.ARGB_8888)
        compose.runOnIdle { decor.draw(Canvas(bitmap)) }
        val file = File("build/qa-screenshots/$name.png")
        checkNotNull(file.parentFile).mkdirs()
        file.outputStream().use { check(bitmap.compress(Bitmap.CompressFormat.PNG, 100, it)) }
    }

    @Test fun simulatedSaleUpdatesReportAndAllowsAnotherSale() {
        compose.onNodeWithText("SIMULADO · Sin dinero real").assertIsDisplayed()
        compose.onNodeWithText("Iniciar sesión").assertIsDisplayed()
        screenshot("login-simulado")
        scrollToText("Entrar en simulación").performClick()
        screenshot("inicio-simulado")
        compose.onNodeWithText("Cobrar\ncon Pey").performClick()
        compose.onNodeWithContentDescription("Agregar Refresco 600 ml").performScrollTo().performClick()
        scrollToText("Revisar y cobrar").performClick()
        compose.onNodeWithText("Crear QR").performClick()
        scrollToText("Simular confirmación · sin dinero").performClick()
        scrollToText("¡Cobro exitoso!").assertIsDisplayed()
        screenshot("confirmacion-simulada")
        scrollToText("Confirmación SIMULADA. No hubo pago.").assertIsDisplayed()
        scrollToText("Nuevo cobro").performClick()
        compose.onNodeWithText("Reportes").performClick()
        scrollToText("Número de ventas: 1").assertIsDisplayed()
        scrollToText("Cobrado por CoDi: $0.01").assertIsDisplayed()
    }

    @Test fun inventorySearchEmptyAndBackPreserveNavigation() {
        compose.onNodeWithText("Soy empleado").performClick()
        scrollToText("TIENDITA-DEMO").assertIsDisplayed()
        scrollToText("Entrar en simulación").performClick()
        compose.onNodeWithText("Hola, Empleado de ejemplo").assertIsDisplayed()
        compose.onAllNodesWithText("Inventario").onFirst().performClick()
        compose.onNodeWithText("Buscar producto").performTextInput("producto que no existe")
        compose.onNodeWithText("No encontramos productos con ese nombre.").assertIsDisplayed()
        compose.activityRule.scenario.onActivity { it.onBackPressedDispatcher.onBackPressed() }
        compose.onNodeWithText("Cobrar\ncon Pey").assertIsDisplayed()
    }

    @Test fun registrationCanBeAbandonedAndCompletesOnlyAsMockup() {
        scrollToText("¿Tienes una tienda? Crear cuenta demo").performClick()
        compose.onNodeWithText("Crear cuenta").assertIsDisplayed()
        screenshot("registro-simulado")
        compose.activityRule.scenario.onActivity { it.onBackPressedDispatcher.onBackPressed() }
        compose.onNodeWithText("Iniciar sesión").assertIsDisplayed()
        scrollToText("¿Tienes una tienda? Crear cuenta demo").performClick()
        scrollToText("Simular registro de mi tienda").performClick()
        compose.onNodeWithText("Registro simulado").assertIsDisplayed()
        compose.onNodeWithText("Volver", useUnmergedTree = true).performClick()
        compose.onNodeWithText("Registro simulado").assertDoesNotExist()
        scrollToText("Simular registro de mi tienda").performClick()
        compose.onNodeWithText("Continuar en simulación").performClick()
        compose.onNodeWithText("Hola, Dueña de ejemplo").assertIsDisplayed()
        compose.onNodeWithText("SIMULADO · Sin dinero real").assertIsDisplayed()
    }

    @Test fun socialMockupsStayLocalAndAllowReturningToLogin() {
        scrollToText("Google · demo").performClick()
        compose.onNodeWithText("No conectamos con Google ni verificamos una identidad. Solo abriremos el perfil de ejemplo elegido.").assertIsDisplayed()
        compose.onNodeWithText("Volver", useUnmergedTree = true).performClick()
        scrollToText("Apple · demo").performClick()
        compose.onNodeWithText("No conectamos con Apple ni verificamos una identidad. Solo abriremos el perfil de ejemplo elegido.").assertIsDisplayed()
        compose.onNodeWithText("Continuar en simulación").performClick()
        compose.onNodeWithText("Hola, Dueña de ejemplo").assertIsDisplayed()
        compose.onNodeWithContentDescription("Conexión y alcance").performClick()
        scrollToText("Volver al login simulado").performClick()
        compose.onNodeWithText("Iniciar sesión").assertIsDisplayed()
        compose.onNodeWithText("Hola, Dueña de ejemplo").assertDoesNotExist()
    }

    @Test fun mockProfileCannotReplaceAnActiveCharge() {
        scrollToText("Entrar en simulación").performClick()
        compose.onNodeWithText("Cobrar\ncon Pey").performClick()
        compose.onNodeWithContentDescription("Agregar Refresco 600 ml").performScrollTo().performClick()
        compose.onNodeWithContentDescription("Conexión y alcance").performClick()
        scrollToText("Volver al login simulado").assertIsNotEnabled()
        compose.activityRule.scenario.onActivity { it.onBackPressedDispatcher.onBackPressed() }
        scrollToText("Revisar y cobrar").performClick()
        compose.onNodeWithText("Crear QR").performClick()
        compose.onNodeWithContentDescription("Conexión y alcance").performClick()
        scrollToText("Volver al login simulado").assertIsNotEnabled()
        compose.activityRule.scenario.onActivity { it.onBackPressedDispatcher.onBackPressed() }
        compose.onNodeWithText("Iniciar sesión").assertDoesNotExist()
        scrollToText("Simular confirmación · sin dinero").assertIsDisplayed()
    }
}
