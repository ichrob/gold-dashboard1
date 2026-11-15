package ch.bob.degirocompanion
import org.junit.Assert.*
import org.junit.Test
class RemoteGestureBudgetTest {
    @Test fun retryIsBoundedAndDifferentSessionStartsFresh() {
        val b=RemoteGestureBudget()
        assertTrue(b.take("one",1,"SEARCH","Gold"))
        assertFalse(b.take("one",1,"SEARCH","Gold"))
        assertTrue(b.take("one",1,"FOCUS","Gold"))
        assertTrue(b.take("two",1,"SEARCH","Gold"))
        b.clear()
        assertTrue(b.take("two",1,"SEARCH","Gold"))
    }
    @Test fun invalidOrUnboundedRequestsAreRejected() {
        val b=RemoteGestureBudget()
        assertFalse(b.take("",1,"SEARCH","Gold"))
        assertFalse(b.take("one",-1,"SEARCH","Gold"))
        assertFalse(b.take("one",1,"BUY","Gold"))
        assertFalse(b.take("one",1,"RESULT","not-an-isin"))
        for(i in 1..12) assertTrue(b.take("one",i,"SEARCH","Gold"))
        assertFalse(b.take("one",13,"SEARCH","Gold"))
    }
}
