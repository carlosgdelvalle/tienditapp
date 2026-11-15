package mx.abarpay.mobile

import kotlinx.coroutines.runBlocking
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

/**
 * Contrato v3.1 · imágenes de producto: parseo defensivo de `imageUrl`, cuerpo del
 * CRUD, validación https/≤500 y respaldo al emoji por categoría cuando no hay URL.
 */
class ImageUrlTest {
    @Test fun readProductParsesImageUrlAndToleratesMissingOrBlank() {
        val withUrl = JSONObject(
            """{"id":7,"name":"Coca-Cola","unit":"pieza","priceCents":1800,"stockMilli":1000,
               "imageUrl":"https://images.openfoodfacts.org/images/products/coca.jpg"}""",
        )
        assertEquals(
            "https://images.openfoodfacts.org/images/products/coca.jpg",
            readProduct(withUrl).imageUrl,
        )
        // Sin campo, null explícito o blank: el producto no tiene imagen y usará emoji.
        assertNull(readProduct(JSONObject("""{"id":7,"name":"Coca-Cola"}""")).imageUrl)
        assertNull(readProduct(JSONObject("""{"id":7,"name":"Coca-Cola","imageUrl":null}""")).imageUrl)
        assertNull(readProduct(JSONObject("""{"id":7,"name":"Coca-Cola","imageUrl":"   "}""")).imageUrl)
        // Alias snake_case por si un serializador viejo manda image_url.
        assertEquals(
            "https://x.mx/agua.png",
            readProduct(JSONObject("""{"id":8,"name":"Agua","image_url":"https://x.mx/agua.png"}""")).imageUrl,
        )
    }

    @Test fun readInventoryItemParsesImageUrl() {
        val json = JSONObject("""{"productId":1,"name":"Coca-Cola","imageUrl":"https://x.mx/coca.jpg"}""")
        assertEquals("https://x.mx/coca.jpg", readInventoryItem(json).imageUrl)
        assertNull(readInventoryItem(JSONObject("""{"productId":1,"name":"Coca-Cola"}""")).imageUrl)
    }

    @Test fun catalogBodySendsOptionalImageUrlAndNullToClearIt() {
        val body = catalogBody(CatalogDraft(name = "Agua", priceCents = 1500, imageUrl = " https://x.mx/agua.jpg "))
        assertEquals("https://x.mx/agua.jpg", body.getString("imageUrl"))
        // Sin URL se manda null: al editar, guardar vacío borra la imagen del servidor.
        val cleared = catalogBody(CatalogDraft(name = "Agua", priceCents = 1500))
        assertTrue(cleared.has("imageUrl"))
        assertTrue(cleared.isNull("imageUrl"))
        val patch = catalogBody(CatalogDraft(name = "Agua", priceCents = 1500), includeNulls = false)
        assertFalse(patch.has("imageUrl"))
    }

    @Test fun imageUrlMustBeHttpsAndAtMost500Characters() {
        assertTrue(imageUrlValid(null))
        assertTrue(imageUrlValid(""))
        assertTrue(imageUrlValid("   "))
        assertTrue(imageUrlValid("https://x.mx/a.jpg"))
        assertFalse(imageUrlValid("http://x.mx/a.jpg"))
        assertFalse(imageUrlValid("ftp://x.mx/a.jpg"))
        assertFalse(imageUrlValid("x.mx/a.jpg"))
        assertFalse(imageUrlValid("https://x.mx/" + "a".repeat(IMAGE_URL_MAX_LENGTH)))
        assertEquals(
            "La URL de imagen debe empezar con https://",
            imageUrlProblem("http://x.mx/a.jpg"),
        )
        // El formulario no deja guardar con una URL inválida.
        assertFalse(catalogDraftReady(CatalogDraft(name = "Agua", priceCents = 1500, imageUrl = "http://x.mx/a.jpg")))
        assertTrue(catalogDraftReady(CatalogDraft(name = "Agua", priceCents = 1500, imageUrl = "https://x.mx/a.jpg")))
        assertTrue(catalogDraftReady(CatalogDraft(name = "Agua", priceCents = 1500)))
    }

    @Test fun productWithoutUsableImageFallsBackToCategoryEmoji() {
        val coca = Product(1, "Coca-Cola", "pieza", 1800, 24000, category = "Bebidas")
        assertNull(productImageUrl(coca))
        assertEquals("🥤", categoryEmoji(coca.category))
        assertEquals("https://x.mx/coca.jpg", productImageUrl(coca.copy(imageUrl = "https://x.mx/coca.jpg")))
        // Una URL no https no se intenta cargar: se queda el emoji.
        assertNull(productImageUrl(coca.copy(imageUrl = "http://x.mx/coca.jpg")))
        assertNull(productImageUrl(coca.copy(imageUrl = " ")))
    }

    @Test fun catalogDraftKeepsImageUrl() {
        val product = Product(1, "Agua", "pieza", 1500, 10000, imageUrl = "https://x.mx/agua.jpg")
        assertEquals("https://x.mx/agua.jpg", catalogDraft(product).imageUrl)
        assertNull(catalogDraft(Product(1, "Agua", "pieza", 1500, 10000)).imageUrl)
    }

    @Test fun demoRepositoryStoresClearsAndExposesImageUrl() = runBlocking {
        val demo = DemoRepository()
        val created = demo.createCatalogItem(
            CatalogDraft(name = "Agua imagen", priceCents = 1500, imageUrl = " https://x.mx/agua.jpg "),
        )
        assertEquals("https://x.mx/agua.jpg", created.imageUrl)
        assertEquals(
            "https://x.mx/agua.jpg",
            demo.catalog(limit = 500).items.first { it.id == created.id }.imageUrl,
        )
        assertEquals(
            "https://x.mx/agua.jpg",
            demo.inventory().items.first { it.productId == created.id }.imageUrl,
        )
        // Editar y dejar la URL vacía quita la imagen (vuelve el emoji).
        val cleared = demo.updateCatalogItem(created.id, catalogDraft(created).copy(imageUrl = ""))
        assertNull(cleared.imageUrl)
        // El demo también rechaza URLs no https, como el servidor.
        val error = runCatching {
            demo.createCatalogItem(CatalogDraft(name = "X", priceCents = 100, imageUrl = "http://x.mx/a.jpg"))
        }.exceptionOrNull()
        assertTrue(error is IllegalArgumentException)
    }
}
