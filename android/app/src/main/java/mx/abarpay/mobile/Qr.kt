package mx.abarpay.mobile

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Color
import android.util.Base64
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.produceState
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import com.google.zxing.BarcodeFormat
import com.google.zxing.EncodeHintType
import com.google.zxing.common.BitMatrix
import com.google.zxing.qrcode.QRCodeWriter
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.ByteArrayOutputStream

/** Decodes the server data URL defensively; a bad or missing QR never crashes the sale screen. */
@Composable
internal fun rememberQrBitmap(dataUrl: String): ImageBitmap? {
    val bitmap by produceState<ImageBitmap?>(null, dataUrl) {
        value = withContext(Dispatchers.Default) {
            runCatching {
                require(dataUrl.length <= 3_000_000)
                require(
                    dataUrl.startsWith("data:image/png;base64,") ||
                        dataUrl.startsWith("data:image/jpeg;base64,") ||
                        dataUrl.startsWith("data:image/webp;base64,")
                )
                val raw = Base64.decode(dataUrl.substringAfter(','), Base64.DEFAULT)
                val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
                BitmapFactory.decodeByteArray(raw, 0, raw.size, bounds)
                require(bounds.outWidth in 1..4096 && bounds.outHeight in 1..4096)
                val options = BitmapFactory.Options().apply { inSampleSize = 1 }
                while (maxOf(bounds.outWidth, bounds.outHeight) / options.inSampleSize > 1024) options.inSampleSize *= 2
                BitmapFactory.decodeByteArray(raw, 0, raw.size, options)?.asImageBitmap()
            }.getOrNull()
        }
    }
    return bitmap
}

/** Matriz QR del enlace de invitación (ZXing core, sin red ni servicios de Google). */
internal fun inviteQrMatrix(url: String, size: Int = 640): BitMatrix = QRCodeWriter().encode(
    url,
    BarcodeFormat.QR_CODE,
    size,
    size,
    mapOf(EncodeHintType.MARGIN to 1, EncodeHintType.CHARACTER_SET to "UTF-8"),
)

/** QR listo para dibujar. Si algo falla devolvemos null y la pantalla ofrece el enlace. */
internal fun inviteQrBitmap(url: String, size: Int = 640): Bitmap? = runCatching {
    val matrix = inviteQrMatrix(url, size)
    val pixels = IntArray(matrix.width * matrix.height)
    for (y in 0 until matrix.height) {
        val row = y * matrix.width
        for (x in 0 until matrix.width) {
            pixels[row + x] = if (matrix.get(x, y)) Color.BLACK else Color.WHITE
        }
    }
    Bitmap.createBitmap(pixels, matrix.width, matrix.height, Bitmap.Config.ARGB_8888)
}.getOrNull()

@Composable
internal fun rememberInviteQr(url: String): ImageBitmap? {
    val bitmap by produceState<ImageBitmap?>(null, url) {
        value = withContext(Dispatchers.Default) { inviteQrBitmap(url)?.asImageBitmap() }
    }
    return bitmap
}

/**
 * Foto del onboarding en data URL JPEG. Se reduce para no acercarse al límite de 5 MB
 * del contrato y se comprime sin metadatos: solo la imagen que eligió el dueño.
 */
internal fun storePhotoDataUrl(bitmap: Bitmap, maxSide: Int = 1280, quality: Int = 80): String {
    require(bitmap.width > 0 && bitmap.height > 0) { "La foto está vacía" }
    val scale = minOf(1f, maxSide.toFloat() / maxOf(bitmap.width, bitmap.height))
    val scaled = if (scale < 1f) {
        Bitmap.createScaledBitmap(
            bitmap,
            maxOf(1, (bitmap.width * scale).toInt()),
            maxOf(1, (bitmap.height * scale).toInt()),
            true,
        )
    } else {
        bitmap
    }
    val out = ByteArrayOutputStream()
    scaled.compress(Bitmap.CompressFormat.JPEG, quality, out)
    return "data:image/jpeg;base64," + Base64.encodeToString(out.toByteArray(), Base64.NO_WRAP)
}
