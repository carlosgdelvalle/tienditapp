package mx.abarpay.mobile

import android.app.Application
import android.os.Looper
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.Config

/** Sin actividad de por medio: comprueba que el onboarding sobrevive a un reinicio. */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35])
class OnboardingPersistenceTest {
    private val app get() = RuntimeEnvironment.getApplication()

    private fun idle() {
        shadowOf(Looper.getMainLooper()).idle()
    }

    @Before fun cleanState() {
        app.getSharedPreferences("development_session", 0).edit().clear().commit()
        app.getSharedPreferences("abarpay_owner", 0).edit().clear().commit()
    }

    @Test fun ownerOnboardingPersistsAcrossRestarts() {
        val first = ShopViewModel(app)
        idle()
        first.finishOnboarding(
            goals = listOf("Controlar lo que me deben", "Ver estadísticas avanzadas"),
            ownerName = "Doña Rosa",
            storeName = "La Esquina del Barrio",
            businessType = "Abarrotes",
            photo = null,
        )
        idle()
        assertTrue(first.ui.value.onboarded)
        val prefs = first.getApplication<Application>().getSharedPreferences("abarpay_owner", 0)
        assertTrue(prefs.getBoolean("onboarded_owner", false))
        assertEquals(
            "Controlar lo que me deben|Ver estadísticas avanzadas",
            prefs.getString("owner_goals", null),
        )
        assertEquals("La Esquina del Barrio", first.ui.value.bootstrap?.store?.name)

        val restarted = ShopViewModel(app)
        idle()
        assertTrue(restarted.ui.value.onboarded)
        assertEquals(2, restarted.ui.value.ownerGoals.size)
    }
}
