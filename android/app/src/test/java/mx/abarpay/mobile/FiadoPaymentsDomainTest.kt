package mx.abarpay.mobile

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** Contrato v3.2 · atajos, permisos y formato del historial de fiado. */
class FiadoPaymentsDomainTest {
    @Test fun presetsOnlyFitTheOutstandingBalance() {
        assertEquals(emptyList<Long>(), fiadoAbonoPresets(0))
        assertEquals(emptyList<Long>(), fiadoAbonoPresets(3_500))
        assertEquals(listOf(5_000L), fiadoAbonoPresets(5_000))
        assertEquals(listOf(5_000L), fiadoAbonoPresets(5_300))
        assertEquals(listOf(5_000L, 10_000L), fiadoAbonoPresets(10_000))
        assertEquals(listOf(5_000L, 10_000L), fiadoAbonoPresets(18_000))
        assertEquals(emptyList<Long>(), fiadoAbonoPresets(-100))
    }

    @Test fun ownerAndCanFiadoCanRegisterAbonos() {
        assertTrue(canRegisterAbono(null))
        assertTrue(canRegisterAbono(Employee(1, "Doña Rosa", "owner")))
        assertTrue(canRegisterAbono(Employee(2, "Lupita", "employee", canFiado = true)))
        assertFalse(canRegisterAbono(Employee(5, "Beto", "employee", canFiado = false)))
    }

    @Test fun historyShowsKindSignAndDate() {
        val charge = FiadoEntry(1, "charge", 3_500, createdAt = 1_763_234_400.0)
        val payment = FiadoEntry(2, "payment", 5_000, createdAt = 1_763_238_000.0)
        assertEquals("Cargo", fiadoKindLabel(charge.kind))
        assertEquals("Abono", fiadoKindLabel(payment.kind))
        assertTrue(fiadoSignedAmount(charge).startsWith("+"))
        assertTrue(fiadoSignedAmount(payment).startsWith("−"))
        assertTrue(fiadoSignedAmount(charge).contains(money(3_500)))
        assertEquals("", fiadoDateText(0.0))
        assertTrue(Regex("""\d{2}/\d{2}/\d{4} \d{2}:\d{2}""").matches(fiadoDateText(1_763_234_400.0)))
    }

    @Test fun shortcutTextMatchesTheAmountField() {
        assertEquals("35", cashInputText(3_500))
        assertEquals("50", cashInputText(5_000))
        assertEquals("35.50", cashInputText(3_550))
    }
}
