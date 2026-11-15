package mx.abarpay.mobile

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import coil.compose.SubcomposeAsyncImage
import coil.compose.SubcomposeAsyncImageContent
import coil.request.ImageRequest

/**
 * Contrato v3.1 · miniatura cuadrada del producto con Coil (caché de memoria y
 * disco). Si el producto no trae [Product.imageUrl] —o la carga falla— se dibuja
 * el emoji de la categoría, igual que antes. Se usa en las filas del catálogo de
 * Cobrar, en la hoja del carrito y en la pantalla Catálogo del dueño.
 */
@Composable
internal fun ProductThumbnail(
    product: Product,
    size: Dp,
    modifier: Modifier = Modifier,
    background: Color = Lavender,
    cornerRadius: Dp = 14.dp,
) {
    Box(
        modifier
            .size(size)
            .clip(RoundedCornerShape(cornerRadius))
            .background(background)
            .testTag("miniatura-producto-" + product.id),
        contentAlignment = Alignment.Center,
    ) {
        val url = productImageUrl(product)
        if (url == null) {
            CategoryEmojiFallback(product, size)
        } else {
            SubcomposeAsyncImage(
                model = ImageRequest.Builder(LocalContext.current)
                    .data(url)
                    .crossfade(true)
                    .build(),
                contentDescription = "Imagen de " + product.name,
                contentScale = ContentScale.Crop,
                modifier = Modifier.fillMaxSize().testTag("imagen-producto-" + product.id),
                loading = { CategoryEmojiFallback(product, size) },
                error = { CategoryEmojiFallback(product, size) },
                success = { SubcomposeAsyncImageContent() },
            )
        }
    }
}

/** Respaldo y placeholder: el emoji por categoría que ya usaba la app. */
@Composable
private fun CategoryEmojiFallback(product: Product, size: Dp) {
    Text(
        categoryEmoji(product.category),
        fontSize = (size.value * 0.52f).sp,
        modifier = Modifier.testTag("emoji-producto-" + product.id),
    )
}
