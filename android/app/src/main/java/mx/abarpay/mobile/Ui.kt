package mx.abarpay.mobile

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.ChevronRight
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

internal val Purple = Color(0xFF2A0065)
internal val Violet = Color(0xFF8400FF)
internal val Lavender = Color(0xFFF5F0FB)
internal val Green = Color(0xFF297A00)
internal val Amber = Color(0xFF9A5600)
internal val Muted = Color(0xFF666680)
internal val SoftViolet = Color(0xFFEADFFF)
internal val SoftAmber = Color(0xFFFFF0D9)
internal val SoftGreen = Color(0xFFE4F4DA)

@Composable
internal fun AbarpayTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = lightColorScheme(
            primary = Violet,
            onPrimary = Color.White,
            background = Lavender,
            surface = Color.White,
            onSurface = Purple,
            secondaryContainer = SoftViolet,
        ),
        content = content,
    )
}

@Composable
internal fun Notice(text: String, warning: Boolean = false) {
    Text(
        text,
        Modifier.fillMaxWidth().background(if (warning) SoftAmber else SoftViolet)
            .padding(horizontal = 20.dp, vertical = 9.dp),
        color = Purple,
        fontSize = 12.sp,
        lineHeight = 17.sp,
    )
}

@Composable
internal fun Title(text: String) {
    Text(text, style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
}

@Composable
internal fun SectionLabel(text: String) {
    Text(text, fontSize = 18.sp, fontWeight = FontWeight.Bold)
}

@Composable
internal fun MutedText(text: String, size: Int = 13) {
    Text(text, color = Muted, fontSize = size.sp, lineHeight = (size + 4).sp)
}

@Composable
internal fun Panel(
    modifier: Modifier = Modifier,
    content: @Composable ColumnScope.() -> Unit,
) {
    Card(
        modifier.fillMaxWidth(),
        shape = RoundedCornerShape(22.dp),
        colors = CardDefaults.cardColors(containerColor = Color.White),
        elevation = CardDefaults.cardElevation(defaultElevation = 1.dp),
    ) {
        Column(
            Modifier.padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
            content = content,
        )
    }
}

@Composable
internal fun Action(
    title: String,
    icon: ImageVector,
    subtitle: String? = null,
    primary: Boolean = false,
    onClick: () -> Unit,
) {
    Card(
        onClick = onClick,
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(24.dp),
        colors = CardDefaults.cardColors(
            containerColor = if (primary) Violet else Color.White,
            contentColor = if (primary) Color.White else Purple,
        ),
    ) {
        Row(
            Modifier.padding(20.dp).heightIn(min = if (primary) 78.dp else 52.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            androidx.compose.material3.Icon(icon, null, Modifier.size(if (primary) 42.dp else 30.dp))
            Column(Modifier.weight(1f).padding(horizontal = 16.dp)) {
                Text(title, fontSize = if (primary) 25.sp else 18.sp, fontWeight = FontWeight.Bold)
                if (subtitle != null) Text(subtitle, fontSize = 12.sp, lineHeight = 16.sp)
            }
            androidx.compose.material3.Icon(Icons.Outlined.ChevronRight, null, Modifier.size(20.dp))
        }
    }
}

@Composable
internal fun InfoRow(label: String, value: String, strong: Boolean = false) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        Text(label, Modifier.weight(1f), color = Muted, fontSize = 14.sp)
        Text(value, fontWeight = if (strong) FontWeight.Bold else FontWeight.SemiBold, fontSize = 14.sp)
    }
}
