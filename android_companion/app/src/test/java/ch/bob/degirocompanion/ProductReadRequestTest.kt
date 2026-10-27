package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

class ProductReadRequestTest {
    @Test fun requestRequiresStartAndExpiresWithoutPersisting() {
        ProductReadRequest.cancel()
        assertFalse(ProductReadRequest.attempt(1000))
        ProductReadRequest.start(1000)
        assertTrue(ProductReadRequest.active(60999))
        assertFalse(ProductReadRequest.attempt(61000))
        ProductReadRequest.start(1000)
        assertFalse(ProductReadRequest.active(999))
    }
    @Test fun eventFloodIsThrottledAndHasFiniteBudget() {
        ProductReadRequest.start(1000)
        assertTrue(ProductReadRequest.attempt(1000))
        repeat(999) { assertFalse(ProductReadRequest.attempt(1001 + it.toLong())) }
        for (i in 1..29) assertTrue(ProductReadRequest.attempt(1000 + i * 1000L))
        assertFalse(ProductReadRequest.attempt(31000))
    }
    @Test fun cancellationAndNewStartDoNotReuseOldBudget() {
        ProductReadRequest.start(1000)
        assertTrue(ProductReadRequest.attempt(1000))
        ProductReadRequest.cancel()
        assertFalse(ProductReadRequest.attempt(2000))
        ProductReadRequest.start(3000)
        assertTrue(ProductReadRequest.attempt(3000))
        ProductReadRequest.cancel()
    }
}
