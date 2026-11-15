package mx.abarpay.mobile

import android.view.ViewGroup
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.viewinterop.AndroidView
import androidx.media3.common.MediaItem
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.datasource.RawResourceDataSource
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.ui.AspectRatioFrameLayout
import androidx.media3.ui.PlayerView
import kotlinx.coroutines.delay

/**
 * Splash de la app: el video solo en el primer arranque tras instalar;
 * la imagen de marca en cada arranque en frío posterior.
 */
@Composable
internal fun SplashGate(onDone: () -> Unit) {
    val context = LocalContext.current
    val prefs = remember { context.getSharedPreferences("splash", 0) }
    var introSeen = remember { prefs.getBoolean("splash_intro_seen", false) }
    if (!introSeen) {
        SplashVideoScreen(
            onDone = {
                prefs.edit().putBoolean("splash_intro_seen", true).commit()
                introSeen = true
            },
        )
    } else {
        SplashImageScreen(onDone = onDone)
    }
}

@Composable
private fun SplashImageScreen(onDone: () -> Unit) {
    LaunchedEffect(Unit) {
        delay(900)
        onDone()
    }
    Box(Modifier.fillMaxSize().background(Color(0xFF2A0065))) {
        Image(
            painter = painterResource(R.drawable.splash_brand),
            contentDescription = "Abarpay",
            modifier = Modifier.fillMaxSize(),
            contentScale = ContentScale.Crop,
        )
    }
}

/** Video intro a pantalla completa: mudo, sin controles, tocar para saltar, máx. ~5 s. */
@Composable
private fun SplashVideoScreen(onDone: () -> Unit) {
    val context = LocalContext.current
    val player = remember {
        ExoPlayer.Builder(context).build().apply {
            volume = 0f
            repeatMode = Player.REPEAT_MODE_OFF
        }
    }
    val playerView = remember {
        PlayerView(context).apply {
            resizeMode = AspectRatioFrameLayout.RESIZE_MODE_ZOOM
            useController = false
            layoutParams = ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT,
            )
        }
    }
    LaunchedEffect(Unit) {
        delay(5_000)
        onDone()
    }
    DisposableEffect(Unit) {
        val listener = object : Player.Listener {
            override fun onPlaybackStateChanged(playbackState: Int) {
                if (playbackState == Player.STATE_ENDED) onDone()
            }

            override fun onPlayerError(error: PlaybackException) {
                onDone()
            }
        }
        player.addListener(listener)
        player.setMediaItem(
            MediaItem.fromUri(RawResourceDataSource.buildRawResourceUri(R.raw.splashintro)),
        )
        player.prepare()
        player.playWhenReady = true
        playerView.player = player
        onDispose {
            playerView.player = null
            player.release()
        }
    }
    Box(Modifier.fillMaxSize().background(Color(0xFF2A0065)).clickable { onDone() }) {
        AndroidView(
            factory = { playerView },
            modifier = Modifier.fillMaxSize(),
        )
        // Marca discreta encima del video.
        Image(
            painter = painterResource(R.drawable.ic_abarpay),
            contentDescription = null,
            modifier = Modifier.align(Alignment.Center),
        )
    }
}
