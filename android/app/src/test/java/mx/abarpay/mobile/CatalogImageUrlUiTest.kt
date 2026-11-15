package mx.abarpay.mobile

import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performTextClearance
import androidx.compose.ui.test.performTextInput
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/**
 * v3.1 · formulario del catálogo del dueño: campo opcional «URL de imagen» con
 * validación https y borrado al dejar el campo vacío.
 */
class CatalogImageUrlUiTest : AppUiTest() {
    private val imageUrl = "https://images.openfoodfacts.org/images/products/750/agua.jpg"

    @Test fun ownerSetsAndClearsOptionalImageUrl() {
        loginOwner()
        scrollToTag("abrir-catalogo")
        compose.onNodeWithTag("abrir-catalogo").performClick()
        compose.waitUntil(15_000) { model().ui.value.catalogOpen && !model().ui.value.busy }

        compose.onNodeWithTag("catalogo-nuevo").performScrollTo().performClick()
        compose.onNodeWithTag("form-nombre").performScrollTo().performTextInput("Agua con imagen")
        compose.onNodeWithTag("form-precio").performScrollTo().performTextInput("15")
        // http:// no es admisible: el campo lo marca y no deja guardar.
        compose.onNodeWithTag("form-imagen").performScrollTo().performTextInput("http://x.mx/agua.jpg")
        compose.onNodeWithTag("form-guardar").performScrollTo().assertIsNotEnabled()
        compose.onNodeWithTag("form-imagen").performScrollTo().performTextClearance()
        compose.onNodeWithTag("form-imagen").performTextInput(imageUrl)
        capture("12-form-url-imagen")
        compose.onNodeWithTag("form-guardar").performScrollTo().performClick()
        compose.waitUntil(15_000) {
            !model().ui.value.busy &&
                model().ui.value.catalog?.items?.any { it.name == "Agua con imagen" } == true
        }
        val created = model().ui.value.catalog!!.items.first { it.name == "Agua con imagen" }
        assertEquals(imageUrl, created.imageUrl)

        // Edición: limpiar la URL la quita del artículo (la app vuelve al emoji).
        compose.onNodeWithTag("catalogo-buscar").performScrollTo().performTextInput("Agua con imagen")
        compose.onNodeWithTag("editar-" + created.id).performScrollTo()
        capture("12-catalogo-url-imagen")
        compose.onNodeWithTag("editar-" + created.id).performClick()
        compose.onNodeWithTag("form-imagen").performScrollTo().performTextClearance()
        compose.onNodeWithTag("form-guardar").performScrollTo().performClick()
        compose.waitUntil(15_000) {
            !model().ui.value.busy &&
                model().ui.value.catalog?.items?.firstOrNull { it.id == created.id }?.imageUrl == null
        }
        assertNull(model().ui.value.catalog!!.items.first { it.id == created.id }.imageUrl)
    }
}
