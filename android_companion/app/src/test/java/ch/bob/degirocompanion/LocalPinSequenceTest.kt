package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

class LocalPinSequenceTest {
    @Test fun staleCallbackCannotCompleteOrCancelTheFollowingPress() {
        val sequence = LocalPinSequence(byteArrayOf(48,49,50,51,52))
        sequence.reserve(true); val old = sequence.ticket; sequence.completed(old, true)
        sequence.reserve(true)
        sequence.completed(old, true); sequence.completed(old, false)
        assertTrue(sequence.pending); assertNull(sequence.reserve(true))
        sequence.completed(sequence.ticket, true)
        assertEquals(2, sequence.reserve(true))
    }

    @Test fun preservesLeadingZeroAndReservesEachPressBeforeItsCallback() {
        val input = byteArrayOf(48, 49, 50, 51, 52) // Synthetic fixture only.
        val sequence = LocalPinSequence(input); input.fill(0)
        for (digit in 0..4) {
            assertEquals(digit, sequence.reserve(true))
            repeat(3) { assertNull(sequence.reserve(true)) }
            sequence.completed(sequence.ticket, true); sequence.completed(sequence.ticket, true)
        }
        assertTrue(sequence.complete); assertNull(sequence.reserve(true))
    }
    @Test fun cancellationInvalidLayoutAndLateCallbacksNeverRetry() {
        for (at in 0..4) {
            val sequence = LocalPinSequence(byteArrayOf(48, 49, 50, 51, 52))
            repeat(at) { sequence.reserve(true); sequence.completed(sequence.ticket, true) }
            sequence.reserve(true); sequence.completed(sequence.ticket, false); sequence.completed(sequence.ticket, true)
            repeat(5) { assertNull(sequence.reserve(true)) }
            assertFalse(sequence.complete)
        }
        val invalid = LocalPinSequence(byteArrayOf(48, 49, 50, 51, 52))
        assertNull(invalid.reserve(false)); invalid.completed(invalid.ticket, true); assertNull(invalid.reserve(true))
    }
    @Test fun refusesMalformedInputs() {
        for (input in listOf(byteArrayOf(), byteArrayOf(1,2,3,4,5), ByteArray(6) { 48 }))
            assertThrows(IllegalArgumentException::class.java) { LocalPinSequence(input) }
    }
}
