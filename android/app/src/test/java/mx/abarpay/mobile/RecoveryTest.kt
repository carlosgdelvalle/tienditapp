package mx.abarpay.mobile

import kotlinx.coroutines.runBlocking
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35])
class RecoveryTest {
    private val app get() = RuntimeEnvironment.getApplication()
    private val prefs get() = app.getSharedPreferences("development_session", 0)

    @Before fun clearSession() { assertTrue(prefs.edit().clear().commit()) }

    @Test fun knownSaleWithoutServerRemainsBlockedAndNeverPollsSimulation() = runBlocking {
        val sale = Sale("real-reference", 1800, 1, status = "pending", paymentMethod = PAYMENT_PEY, qrId = "qr-1")
        assertTrue(prefs.edit().putString("sale", saleJson(sale).toString()).commit())
        val vm = ShopViewModel(app)
        assertFalse(vm.ui.value.simulated)
        assertTrue(vm.ui.value.uncertain)
        val message = vm.ui.value.message
        vm.poll()
        assertEquals(message, vm.ui.value.message)
        assertEquals(sale, vm.ui.value.sale)
        assertFalse(vm.ui.value.sale!!.settled)
    }

    @Test fun corruptStoredSaleFailsClosed() {
        assertTrue(prefs.edit().putString("sale", "corrupt").commit())
        val vm = ShopViewModel(app)
        assertTrue(vm.ui.value.uncertain)
        assertFalse(vm.ui.value.simulated)
        assertNull(vm.ui.value.sale)
    }

    @Test fun interruptedCreationStaysBlockedAfterRestart() {
        assertTrue(prefs.edit().putBoolean("creating", true).commit())
        val vm = ShopViewModel(app)
        assertTrue(vm.ui.value.uncertain)
        assertNull(vm.ui.value.sale)
        assertTrue(prefs.getBoolean("creating", false))
    }

    @Test fun storedSaleKeepsPaymentMethodAndChange() {
        val sale = Sale("cash-reference", 3600, 3600, status = "paid_cash", paymentMethod = PAYMENT_CASH,
            cashReceivedCents = 5000, changeCents = 1400)
        assertTrue(prefs.edit().putString("sale", saleJson(sale).toString()).commit())
        val vm = ShopViewModel(app)
        assertFalse(vm.ui.value.simulated)
        assertEquals(sale, vm.ui.value.sale)
        assertEquals(1400L, vm.ui.value.sale!!.changeCents)
        assertTrue(vm.ui.value.sale!!.settled)
    }
}
