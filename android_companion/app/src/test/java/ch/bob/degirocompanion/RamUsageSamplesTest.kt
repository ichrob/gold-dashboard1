package ch.bob.degirocompanion

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class RamUsageSamplesTest {
    @Test fun sampledStartPeakAndEndPreserveOrder() {
        val m = RamUsageSamples()
        m.record(102400L, 25600L)
        m.record(153600L, 30720L)
        m.record(122880L, 20480L)
        assertEquals(3, m.sampleCount)
        assertEquals(102400L, m.startPssKiB)
        assertEquals(153600L, m.peakPssKiB)
        assertEquals(122880L, m.endPssKiB)
        assertEquals(30720L, m.peakHeapKiB)
        assertEquals(150.0, RamUsageSamples.toMiB(m.peakPssKiB)!!, 0.001)
    }

    @Test fun missingSampleCannotFabricateRamValues() {
        val m = RamUsageSamples()
        m.record(-1L, 40960L)
        assertEquals(0, m.sampleCount)
        assertNull(RamUsageSamples.toMiB(m.startPssKiB))
        m.record(1024L, 2048L)
        assertEquals(1, m.sampleCount)
        assertEquals(1.0, RamUsageSamples.toMiB(m.peakPssKiB)!!, 0.001)
    }
}
