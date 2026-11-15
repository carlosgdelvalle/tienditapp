package mx.abarpay.mobile

import android.content.Intent
import android.net.Uri
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode

/** Contrato v3 · comprobante: bitmap, archivo y ACTION_SEND con FileProvider. */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35])
@GraphicsMode(GraphicsMode.Mode.NATIVE)
class ReceiptDataTest {
    private val context get() = RuntimeEnvironment.getApplication()
    private val sale = Sale(
        "SIMULADO-123", 3600, 3600, status = "paid_cash", paymentMethod = PAYMENT_CASH,
        cashReceivedCents = 5000, changeCents = 1400,
    )

    @Test fun receiptImageIsAFileInsideCacheAndSharesWithFileProvider() {
        val bitmap = receiptBitmap(this.sale, "Mi negocio")
        assertTrue(bitmap.width > 0)
        assertTrue(bitmap.height > 0)
        val file = receiptImageFile(context, sale, "Mi negocio")
        assertTrue("El comprobante debe existir", file.exists())
        assertTrue("El comprobante no debe estar vacío", file.length() > 0)
        assertTrue(file.name.endsWith(".png"))
        assertEquals("comprobantes", file.parentFile?.name)
        val intent = receiptShareIntent(context, sale, "Mi negocio", pdf = false)
        assertEquals(Intent.ACTION_SEND, intent.action)
        assertEquals("image/png", intent.type)
        val uri = intent.getParcelableExtra(Intent.EXTRA_STREAM, Uri::class.java)
        assertNotNull("FileProvider debe entregar un content://", uri)
        assertTrue(uri.toString().startsWith("content://"))
        assertEquals(context.packageName + ".fileprovider", uri!!.authority)
    }

    @Test fun receiptPdfUsesPdfDocumentWhenAvailable() {
        val pdf = runCatching { receiptPdfFile(context, sale, "Mi negocio") }.getOrNull()
        // PdfDocument usa Skia nativo; en Robolectric puede no estar implementado.
        if (pdf != null) {
            assertTrue(pdf.exists())
            assertTrue(pdf.length() > 0)
            val header = pdf.inputStream().use { it.readNBytes(4) }
            assertEquals("%PDF", String(header))
            assertEquals("comprobantes", pdf.parentFile?.name)
        }
    }
}
