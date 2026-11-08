package mx.abarpay.mobile

import android.graphics.Bitmap
import android.graphics.Canvas
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import java.io.File
import org.junit.Rule
import org.junit.Test
import org.junit.rules.ExternalResource
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35], qualifiers = "w390dp-h844dp")
@GraphicsMode(GraphicsMode.Mode.NATIVE)
class MobileFlowTest {
    @get:Rule(order = 0) val cleanSession = object : ExternalResource() {
        override fun before() {
            RuntimeEnvironment.getApplication()
                .getSharedPreferences("development_session", 0).edit().clear().commit()
        }
    }
    @get:Rule(order = 1) val compose = createAndroidComposeRule<MainActivity>()

    private fun scrollTo(text: String): SemanticsNodeInteraction {
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

    private fun login() {
        compose.onNodeWithText("SIMULADO · Sin dinero real").assertIsDisplayed()
        screenshot("01-login-simulado")
        scrollTo("Entrar en simulación").performClick()
    }

    private fun addCokes(times: Int) {
        repeat(times) {
            compose.onNode(hasScrollToIndexAction()).performScrollToKey("product-1")
            compose.onNodeWithContentDescription("Agregar Coca-Cola 600 ml").performClick()
        }
    }

    @Test fun ownerCashSaleShowsChangeAndReportsIt() {
        login()
        compose.onNodeWithText("Hola, Doña Rosa").assertIsDisplayed()
        screenshot("02-inicio")
        compose.onNodeWithTag("tab-Cobrar").performClick()
        addCokes(2)
        screenshot("03-carrito")
        scrollTo("Forma de pago")
        compose.onNodeWithTag("efectivo-recibido").performScrollTo().performTextInput("100")
        scrollTo("Cambio: $64.00").assertIsDisplayed()
        scrollTo("Cobrar en efectivo").performClick()
        scrollTo("Cobro en efectivo registrado").assertIsDisplayed()
        screenshot("04-cobro-efectivo")
        scrollTo("Cambio: $64.00").assertIsDisplayed()
        scrollTo("Nuevo cobro").performClick()
        compose.onNodeWithTag("tab-Reportes").performClick()
        scrollTo("Cobrado: $36.00").assertIsDisplayed()
    }

    @Test fun peyQrOnlySucceedsAfterServerConfirmation() {
        login()
        compose.onNodeWithTag("tab-Cobrar").performClick()
        addCokes(1)
        scrollTo("Forma de pago")
        compose.onNodeWithTag("pago-pey").performClick()
        scrollTo("Generar QR PEY").performClick()
        scrollTo("Cobro con PEY").assertIsDisplayed()
        screenshot("05-pey-pendiente")
        scrollTo("SIMULADO · Este símbolo no sirve para pagar").assertIsDisplayed()
        scrollTo("Simular confirmación · sin dinero").performClick()
        scrollTo("¡Pago PEY confirmado!").assertIsDisplayed()
        screenshot("06-pey-confirmado")
    }

    @Test fun fiadoSaleAddsChargeAndAbonoReducesBalance() {
        login()
        compose.onNodeWithTag("tab-Cobrar").performClick()
        addCokes(1)
        scrollTo("Forma de pago")
        compose.onNodeWithTag("pago-fiado").performClick()
        scrollTo("Doña Mari (ejemplo) · $35.00").performClick()
        scrollTo("Cobrar a fiado").performClick()
        scrollTo("Fiado registrado").assertIsDisplayed()
        scrollTo("Saldo después de la venta").assertIsDisplayed()
        scrollTo("Nuevo cobro").performClick()
        compose.onNodeWithTag("tab-Fiado").performClick()
        compose.onNodeWithText("Doña Mari (ejemplo)").performClick()
        scrollTo("Saldo pendiente").assertIsDisplayed()
        screenshot("07-fiado-detalle")
        compose.onNodeWithTag("abono-monto").performScrollTo().performTextInput("3")
        scrollTo("Registrar abono").performClick()
        compose.onNodeWithText("Abono registrado. Saldo: $50.00.").assertIsDisplayed()
    }

    @Test fun employeeCanAdjustInventoryByOneUnit() {
        compose.onNodeWithText("Soy empleado").performClick()
        scrollTo("Entrar en simulación").performClick()
        compose.onNodeWithText("Hola, Lupita").assertIsDisplayed()
        compose.onNodeWithTag("tab-Inventario").performClick()
        scrollTo("Stock: 24 pza · 24000 milli").assertIsDisplayed()
        screenshot("08-inventario")
        compose.onNodeWithContentDescription("Sumar una unidad de Coca-Cola 600 ml").performScrollTo().performClick()
        scrollTo("Stock: 25 pza · 25000 milli").assertIsDisplayed()
    }

    @Test fun voiceAndBarcodeEntriesAreExposedWithoutCloudDependencies() {
        login()
        compose.onNodeWithTag("tab-Cobrar").performClick()
        compose.onNodeWithContentDescription("Dictar venta").assertIsDisplayed()
        compose.onNodeWithText("Escanear código").assertIsDisplayed()
        compose.onNodeWithText("Escribir venta o código").performClick()
        compose.onNodeWithText("O escribe el código").assertIsDisplayed()
    }
}