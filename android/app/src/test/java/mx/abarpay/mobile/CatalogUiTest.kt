package mx.abarpay.mobile

import androidx.compose.ui.test.*
import org.junit.Assert.*
import org.junit.Test

/** Contrato v3 · catálogo del dueño desde Inicio: búsqueda, chips, alta, edición y borrado. */
class CatalogUiTest : AppUiTest() {
    @Test fun ownerManagesCatalogFromHome() {
        loginOwner()
        scrollToTag("abrir-catalogo")
        compose.onNodeWithTag("abrir-catalogo").performClick()
        compose.waitUntil(15_000) { model().ui.value.catalogOpen && !model().ui.value.busy }
        compose.onNodeWithText("Catálogo").assertExists()
        // El catálogo demo es grande: LazyColumn, chips y conteo.
        assertTrue(model().ui.value.catalog!!.items.size >= 55)
        compose.onNodeWithText("Mostrando " + model().ui.value.catalog!!.items.size + " de " + model().ui.value.catalog!!.total + " artículos.").assertExists()

        val total = model().ui.value.catalog!!.total
        // Búsqueda local por nombre (el contador refleja el filtro).
        compose.onNodeWithTag("catalogo-buscar").performScrollTo().performTextInput("Coca")
        compose.onNodeWithText("Mostrando 1 de " + total + " artículos.").assertExists()
        scrollToText("Coca-Cola 600 ml").assertExists()
        compose.onNodeWithTag("catalogo-buscar").performTextClearance()

        // Chips de categoría.
        compose.onNodeWithTag("categoria-bebidas").performScrollTo().performClick()
        compose.onNodeWithText("Mostrando 8 de " + total + " artículos.").assertExists()
        compose.onNodeWithTag("categoria-todas").performScrollTo().performClick()
        compose.onNodeWithText("Mostrando " + total + " de " + total + " artículos.").assertExists()
        // Favoritos/rápidos.
        compose.onNodeWithTag("catalogo-rapidos").performScrollTo().performClick()
        compose.onNodeWithText("Mostrando 8 de " + total + " artículos.").assertExists()
        compose.onNodeWithTag("catalogo-rapidos").performScrollTo().performClick()

        // Alta de un servicio: sin controles de stock y sin límite.
        compose.onNodeWithTag("catalogo-nuevo").performScrollTo().performClick()
        compose.onNodeWithTag("form-nombre").performScrollTo().performTextInput("Corte express")
        compose.onNodeWithTag("form-precio").performScrollTo().performTextInput("80")
        compose.onNodeWithTag("form-kind-servicio").performScrollTo().performClick()
        compose.onNodeWithTag("form-stock").assertDoesNotExist()
        compose.onNodeWithTag("form-duracion").performScrollTo().performTextInput("20")
        compose.onNodeWithTag("form-guardar").performScrollTo().performClick()
        compose.waitUntil(15_000) {
            !model().ui.value.busy && model().ui.value.catalog?.items?.any { it.name == "Corte express" } == true
        }
        val created = model().ui.value.catalog!!.items.first { it.name == "Corte express" }
        assertEquals(KIND_SERVICIO, created.kind)
        assertTrue(created.unlimitedStock)
        assertEquals(8000L, created.priceCents)
        assertEquals(20, created.durationMinutes)

        // Edición.
        compose.onNodeWithTag("catalogo-buscar").performScrollTo().performTextInput("Corte express")
        compose.onNodeWithText("Mostrando 1 de " + (total + 1) + " artículos.").assertExists()
        compose.onNodeWithTag("editar-" + created.id).performScrollTo().performClick()
        compose.onNodeWithTag("form-precio").performScrollTo().performTextClearance()
        compose.onNodeWithTag("form-precio").performTextInput("95")
        compose.onNodeWithTag("form-guardar").performScrollTo().performClick()
        compose.waitUntil(15_000) {
            !model().ui.value.busy &&
                model().ui.value.catalog?.items?.firstOrNull { it.id == created.id }?.priceCents == 9500L
        }

        // Borrado controlado (sin ventas, se borra).
        compose.onNodeWithTag("borrar-" + created.id).performScrollTo().performClick()
        compose.onNodeWithTag("confirmar-borrar").performClick()
        compose.waitUntil(15_000) {
            !model().ui.value.busy && model().ui.value.catalog?.items?.none { it.id == created.id } == true
        }
        assertEquals("Artículo borrado del catálogo.", model().ui.value.message)
    }
}
