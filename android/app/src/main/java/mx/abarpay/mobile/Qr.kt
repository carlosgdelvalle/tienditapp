package mx.abarpay.mobile

import android.graphics.BitmapFactory
import android.util.Base64
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.produceState
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

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
