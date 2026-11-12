package ch.bob.degirocompanion
import org.junit.Assert.*
import org.junit.Test
class ReadPreparationTicketsTest {
    @Test fun stopThenRestartRejectsLateFirstResponse() {
        val owner=ReadPreparationTickets()
        val first=owner.issue()
        assertTrue(owner.accepts(first))
        owner.cancel()
        assertFalse(owner.accepts(first))
        val second=owner.issue()
        assertFalse(owner.accepts(first))
        assertTrue(owner.accepts(second))
        owner.cancel()
        assertFalse(owner.accepts(second))
    }
}
