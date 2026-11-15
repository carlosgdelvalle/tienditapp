package mx.abarpay.mobile

import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Typeface
import android.graphics.pdf.PdfDocument
import androidx.core.content.FileProvider
import java.io.File

// ---------------------------------------------------------------------------
// Contrato v3 · comprobante compartible como imagen o PDF (ACTION_SEND + FileProvider)
// ---------------------------------------------------------------------------

internal const val RECEIPT_DIR = "comprobantes"
private const val RECEIPT_AUTHORITY_SUFFIX = ".fileprovider"
private const val RECEIPT_TITLE = "Comprobante de venta"

internal fun receiptDir(context: Context): File =
    File(context.cacheDir, RECEIPT_DIR).apply { mkdirs() }

/** Dibuja el comprobante en un bitmap (sin Compose, para poder probarlo sin pantalla). */
internal fun receiptBitmap(sale: Sale, storeName: String, width: Int = 900): Bitmap {
    val rows = receiptRows(storeName, sale)
    val lineHeight = 46
    val padding = 48
    val header = 160
    val height = header + rows.size * lineHeight + 80
    val bitmap = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888)
    val canvas = Canvas(bitmap)
    canvas.drawColor(android.graphics.Color.WHITE)
    val titlePaint = Paint().apply {
        color = android.graphics.Color.rgb(42, 0, 101)
        textSize = 48f
        isAntiAlias = true
        typeface = Typeface.DEFAULT_BOLD
    }
    val labelPaint = Paint().apply {
        color = android.graphics.Color.rgb(102, 102, 128)
        textSize = 30f
        isAntiAlias = true
    }
    val valuePaint = Paint().apply {
        color = android.graphics.Color.rgb(42, 0, 101)
        textSize = 30f
        isAntiAlias = true
        typeface = Typeface.DEFAULT_BOLD
    }
    canvas.drawText("Abarpay", padding.toFloat(), 72f, titlePaint)
    canvas.drawText(RECEIPT_TITLE, padding.toFloat(), 118f, labelPaint)
    var y = header.toFloat()
    rows.forEach { row ->
        canvas.drawText(row.label, padding.toFloat(), y, labelPaint)
        canvas.drawText(row.value, (width - padding).toFloat() - valuePaint.measureText(row.value), y, valuePaint)
        y += lineHeight
    }
    return bitmap
}

internal fun receiptImageFile(context: Context, sale: Sale, storeName: String): File {
    val file = File(receiptDir(context), receiptFileName(sale) + ".png")
    file.outputStream().use { out ->
        check(receiptBitmap(sale, storeName).compress(Bitmap.CompressFormat.PNG, 100, out)) {
            "No se pudo generar la imagen del comprobante"
        }
    }
    return file
}

/** PDF con android.graphics.pdf.PdfDocument, sin servicios de terceros. */
internal fun receiptPdfFile(context: Context, sale: Sale, storeName: String): File {
    val document = PdfDocument()
    try {
        val page = document.startPage(PdfDocument.PageInfo.Builder(595, 842, 1).create())
        val canvas = page.canvas
        val titlePaint = Paint().apply {
            color = android.graphics.Color.rgb(42, 0, 101)
            textSize = 26f
            isAntiAlias = true
            typeface = Typeface.DEFAULT_BOLD
        }
        val labelPaint = Paint().apply {
            color = android.graphics.Color.rgb(102, 102, 128)
            textSize = 13f
            isAntiAlias = true
        }
        val valuePaint = Paint().apply {
            color = android.graphics.Color.rgb(42, 0, 101)
            textSize = 13f
            isAntiAlias = true
            typeface = Typeface.DEFAULT_BOLD
        }
        canvas.drawText("Abarpay", 48f, 64f, titlePaint)
        canvas.drawText(RECEIPT_TITLE, 48f, 90f, labelPaint)
        var y = 130f
        receiptRows(storeName, sale).forEach { row ->
            canvas.drawText(row.label, 48f, y, labelPaint)
            canvas.drawText(row.value, 547f - valuePaint.measureText(row.value), y, valuePaint)
            y += 22f
        }
        document.finishPage(page)
        val file = File(receiptDir(context), receiptFileName(sale) + ".pdf")
        file.outputStream().use { document.writeTo(it) }
        return file
    } finally {
        document.close()
    }
}

internal fun receiptShareIntent(context: Context, sale: Sale, storeName: String, pdf: Boolean): Intent {
    val file = if (pdf) receiptPdfFile(context, sale, storeName) else receiptImageFile(context, sale, storeName)
    val uri = FileProvider.getUriForFile(context, context.packageName + RECEIPT_AUTHORITY_SUFFIX, file)
    return Intent(Intent.ACTION_SEND).apply {
        type = if (pdf) "application/pdf" else "image/png"
        putExtra(Intent.EXTRA_STREAM, uri)
        putExtra(Intent.EXTRA_SUBJECT, "Comprobante de venta")
        putExtra(Intent.EXTRA_TEXT, "Comprobante de venta " + sale.id)
        addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
    }
}

/** Comparte con el selector del sistema. Devuelve un mensaje si algo falló. */
internal fun shareReceipt(context: Context, sale: Sale, storeName: String, pdf: Boolean): String? = runCatching {
    val chooser = Intent.createChooser(receiptShareIntent(context, sale, storeName, pdf), "Compartir comprobante")
        .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
    context.startActivity(chooser)
    null
}.getOrElse { "No pudimos generar el comprobante. Intenta de nuevo." }
