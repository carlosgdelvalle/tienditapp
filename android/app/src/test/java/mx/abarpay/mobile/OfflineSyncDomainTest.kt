package mx.abarpay.mobile

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class OfflineSyncDomainTest {

    @Test
    fun releaseStaysHttpsOnly() {
        assertEquals("https://shop.example", normalizeServer(" https://shop.example/ ", false))
        // Sin excepción de host en release: cualquier http:// se rechaza.
        listOf(
            "http://10.0.2.2:8000",
            "http://192.168.1.10:8000",
            "http://127.0.0.1:8000",
        ).forEach { url -> assertTrue(url, runCatching { normalizeServer(url, false) }.isFailure) }
    }

    @Test
    fun debugAllowsHttpForAnyHost() {
        // Emulador, red local y teléfono físico vía adb reverse.
        listOf(
            "http://10.0.2.2:8000",
            "http://192.168.1.10:8000",
            "http://127.0.0.1:8000",
            "http://localhost:8000",
        ).forEach { url -> assertEquals(url, normalizeServer(url, true)) }
        assertEquals("http://192.168.1.10:8000", normalizeServer("http://192.168.1.10:8000/", true))
    }

    @Test
    fun debugHttpStillEnforcesRootPathAndNoQueryGuards() {
        listOf(
            "http://192.168.1.10:8000/api",
            "http://192.168.1.10:8000?token=x",
            "http://192.168.1.10:8000#secret",
            "http://user:pass@192.168.1.10:8000",
            "https://shop.example/api",
            "https://shop.example?token=value",
            "https://shop.example#secret",
            "https://user:password@shop.example",
        ).forEach { url -> assertTrue(url, runCatching { normalizeServer(url, true) }.isFailure) }
    }
}
