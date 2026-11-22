package mx.abarpay.mobile

import android.os.Looper
import org.junit.Assert.assertEquals
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.Config

/** El carrito en curso sobrevive a cerrar el proceso y se borra al vaciarlo. */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35])
class CartDraftPersistenceTest {
    private val app get() = RuntimeEnvironment.getApplication()
    private val prefs get() = app.getSharedPreferences("development_session", 0)

    private fun idle() {
        shadowOf(Looper.getMainLooper()).idle()
    }

    private fun idleUntil(condition: () -> Boolean) {
        repeat(400) {
            idle()
            if (condition()) return
            Thread.sleep(10)
        }
    }

    @Before fun cleanState() {
        prefs.edit().clear().commit()
        app.getSharedPreferences("abarpay_owner", 0).edit().clear().commit()
    }

    @Test fun draftCartSurvivesAProcessRestart() {
        val first = ShopViewModel(app)
        idleUntil { first.ui.value.bootstrap != null && !first.ui.value.busy }
        first.quantity(1, 1000)
        idleUntil { prefs.getString("cart_draft_v1", null) == "1:1000" }

        val restarted = ShopViewModel(app)
        idle()

        assertEquals(listOf(CartLine(1, 1000)), restarted.ui.value.cart)
    }

    @Test fun emptyingTheCartClearsTheDraft() {
        val model = ShopViewModel(app)
        idleUntil { model.ui.value.bootstrap != null && !model.ui.value.busy }
        model.quantity(1, 1000)
        idleUntil { prefs.getString("cart_draft_v1", null) == "1:1000" }

        model.quantity(1, -1000)
        idleUntil { prefs.getString("cart_draft_v1", null) == "" }

        val restarted = ShopViewModel(app)
        idle()
        assertEquals(emptyList<CartLine>(), restarted.ui.value.cart)
    }
}
