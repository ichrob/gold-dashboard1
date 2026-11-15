package ch.bob.degirocompanion

import kotlin.math.round

/** Process-memory measurements in KiB. No product, account or screen data. */
internal class RamUsageSamples {
    var sampleCount: Int = 0
        private set
    var startPssKiB: Long = -1
        private set
    var peakPssKiB: Long = -1
        private set
    var endPssKiB: Long = -1
        private set
    var peakHeapKiB: Long = -1
        private set

    fun record(pssKiB: Long, heapKiB: Long) {
        if (pssKiB <= 0L) return
        if (sampleCount == 0) startPssKiB = pssKiB
        sampleCount++
        endPssKiB = pssKiB
        peakPssKiB = maxOf(peakPssKiB, pssKiB)
        if (heapKiB >= 0L) peakHeapKiB = maxOf(peakHeapKiB, heapKiB)
    }

    companion object {
        fun toMiB(kib: Long): Double? =
            if (kib < 0L) null else round(kib / 1024.0 * 10.0) / 10.0
    }
}
