package ch.bob.degirocompanion
import org.junit.Assert.*
import org.junit.Test

class PinResetEvidenceTest {
    @Test fun supportsDirectAndNearbyParentActions() {
        for (distance in 0..2) {
            val p = PinResetEvidence()
            p.observe(7, distance, true, false)
            assertEquals(1, p.count())
        }
    }
    @Test fun duplicateLabelsOnSameTargetCountOnce() {
        val p = PinResetEvidence()
        p.observe(7, 0, true, false)
        p.observe(7, 1, true, false)
        assertEquals(1, p.count())
    }
    @Test fun distinctTargetsRemainAmbiguous() {
        val p = PinResetEvidence()
        p.observe(7, 0, true, false)
        p.observe(8, 0, true, false)
        assertEquals(2, p.count())
    }
    @Test fun rejectsDistantOrAbsentOwners() {
        val p = PinResetEvidence()
        p.observe(null, 0, true, false)
        p.observe(7, 3, true, false)
        assertEquals(0, p.count())
    }
    @Test fun rejectsSharedContainersRegardlessOfTraversalOrder() {
        for (first in listOf(true, false)) {
            val p = PinResetEvidence()
            if (first) p.block(7)
            p.observe(7, 1, true, false)
            if (!first) p.block(7)
            assertEquals(0, p.count())
        }
        val p = PinResetEvidence()
        p.observe(7, 1, true, false)
        p.observe(7, 1, false, true)
        assertEquals(0, p.count())
    }
    @Test fun recognizesBackspaceSymbolButNotAnArbitraryCloseIcon() {
        assertEquals(PinLoginEvidence.Marker.DELETE_KEY, PinLoginEvidence.marker("⌫"))
        assertEquals(PinLoginEvidence.Marker.NONE, PinLoginEvidence.marker("×"))
        assertEquals(PinLoginEvidence.Marker.NONE, PinLoginEvidence.marker("X"))
    }
}
