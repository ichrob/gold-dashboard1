package ch.bob.degirocompanion
import org.junit.Assert.*
import org.junit.Test
class TermuxTaskPolicyTest {
    private val session="a".repeat(32)
    @Test fun duplicateConsumedBeforeExecution() {
        val p=TermuxTaskPolicy();val id="b".repeat(32)
        assertTrue(p.accept(session,session,id,120,100,"printf ok"))
        assertFalse(p.accept(session,session,id,120,100,"printf ok"))
        assertFalse(p.accept(session,session,id,120,100,"changed"))
    }
    @Test fun invalidSessionsDeadlinesAndBytesRejected() {
        val p=TermuxTaskPolicy();val id="b".repeat(32)
        assertFalse(p.accept("c".repeat(32),session,id,120,100,"x"))
        assertFalse(p.accept(session,session,id,100,100,"x"))
        assertFalse(p.accept(session,session,id,131,100,"x"))
        assertFalse(p.accept(session,session,id,120,100,"ü".repeat(3001)))
        assertFalse(p.accept(session,session,id,120,100,"x\u0000y"))
        assertTrue(p.accept(session,session,id,120,100,"x"))
    }
}
