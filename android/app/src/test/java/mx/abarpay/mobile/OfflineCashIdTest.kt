package mx.abarpay.mobile

import org.junit.Assert.assertEquals
import org.junit.Test

class OfflineCashIdTest {
    @Test
    fun receiptFolioMatchesThePostgresLedger() {
        assertEquals(
            "675669b0-e8db-57b7-ab3f-d39063c440ff",
            cashSaleId("ca761232-ed42-11ce-bacd-00aa0057b223", "00000000-0000-4000-8000-000000000001"),
        )
    }
}
