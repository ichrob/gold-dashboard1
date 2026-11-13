package ch.bob.degirocompanion
import org.junit.Assert.*
import org.junit.Test
class PhoneDiagnosticRecencyTest {
    @Test fun laterDetailErrorOverridesListDelivery() {
        val first=PhoneDiagnosticRecency.Event("LIST_IMAGES_DELIVERED","2026-11-06T07:36:15Z")
        val second=PhoneDiagnosticRecency.Event("RETURN_NOT_CONFIRMED","2026-11-06T07:37:27Z")
        assertEquals(second,PhoneDiagnosticRecency.latest(first,second))
        assertEquals(second,PhoneDiagnosticRecency.latest(second,first))
    }
    @Test fun invalidTimestampDoesNotReplaceValidEvidence() {
        val known=PhoneDiagnosticRecency.Event("COMPLETE","2026-11-06T07:40:00Z")
        val invalid=PhoneDiagnosticRecency.Event("OTHER","not-a-time")
        assertEquals(known,PhoneDiagnosticRecency.latest(known,invalid))
        assertNull(PhoneDiagnosticRecency.latest(invalid))
    }
}
