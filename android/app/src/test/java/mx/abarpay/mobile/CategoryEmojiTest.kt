package mx.abarpay.mobile

import org.junit.Assert.assertEquals
import org.junit.Test

/** v1.2.1 · miniatura del catálogo por categoría, con respaldo 📦. */
class CategoryEmojiTest {
    @Test fun categoriesMapToTheirThumbnailAndFallBackToBox() {
        assertEquals("🥤", categoryEmoji("Bebidas"))
        assertEquals("🍞", categoryEmoji("Pan"))
        assertEquals("🍞", categoryEmoji("Panadería"))
        assertEquals("🛒", categoryEmoji("Abarrotes"))
        assertEquals("🥛", categoryEmoji("Lácteos"))
        assertEquals("🍟", categoryEmoji("Botanas"))
        assertEquals("🍬", categoryEmoji("Dulces"))
        assertEquals("🌭", categoryEmoji("Embutidos"))
        assertEquals("🧼", categoryEmoji("Limpieza"))
        assertEquals("✂️", categoryEmoji("Cortes"))
        assertEquals("💅", categoryEmoji("Manicure"))
        assertEquals("🍽️", categoryEmoji("Comida"))
        assertEquals("📦", categoryEmoji("Otro"))
        assertEquals("📦", categoryEmoji(null))
        assertEquals("📦", categoryEmoji("  "))
        assertEquals("📦", categoryEmoji("Servicios"))
    }
}
