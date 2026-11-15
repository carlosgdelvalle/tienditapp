package mx.abarpay.mobile

import android.graphics.Bitmap
import android.util.Base64
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35])
@GraphicsMode(GraphicsMode.Mode.NATIVE)
class V2DataTest {
    @Test fun inviteQrEncodesTheLinkWithoutNetwork() {
        val url = "https://abarpay-api.onrender.com/invite/abc123"
        val matrix = inviteQrMatrix(url)
        assertEquals(640, matrix.width)
        assertEquals(640, matrix.height)
        var dark = 0
        for (y in 0 until matrix.height) {
            for (x in 0 until matrix.width) {
                if (matrix.get(x, y)) dark++
            }
        }
        assertTrue("El QR debe tener módulos oscuros", dark > 0)
        val bitmap = inviteQrBitmap(url, size = 320)
        assertEquals(320, bitmap!!.width)
        assertEquals(320, bitmap.height)
    }

    @Test fun onboardingPhotoBecomesADataUrlUnderFiveMegabytes() {
        val bitmap = Bitmap.createBitmap(2000, 1000, Bitmap.Config.ARGB_8888)
        val dataUrl = storePhotoDataUrl(bitmap)
        assertTrue(dataUrl.startsWith("data:image/jpeg;base64,"))
        val raw = Base64.decode(dataUrl.substringAfter(','), Base64.DEFAULT)
        assertTrue(raw.isNotEmpty())
        assertTrue(dataUrl.length < 5_000_000)
    }

}
