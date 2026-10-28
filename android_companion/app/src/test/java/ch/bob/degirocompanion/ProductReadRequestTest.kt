package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

class ProductReadRequestTest {
    @Test fun explicitStartNotifiesReaderWithoutWaitingForWindowEvents() {
        var starts = 0
        ProductReadRequest.onStarted = { starts++ }
        try {
            ProductReadRequest.start(1000)
            assertEquals(1, starts)
            ProductReadRequest.cancel()
            assertEquals(1, starts)
            ProductReadRequest.start(2000)
            assertEquals(2, starts)
        } finally { ProductReadRequest.onStarted = null; ProductReadRequest.cancel() }
    }
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
    @Test fun resumedRequestKeepsOriginalDeadlineAndReleasesOnExpiryOrStop() {
        var releases = 0
        ProductReadRequest.onCancelled = { releases++ }
        try {
            ProductReadRequest.start(1000)
            assertEquals(60000L, ProductReadRequest.remainingMillis(1000))
            assertEquals(10000L, ProductReadRequest.remainingMillis(51000))
            assertEquals(0L, ProductReadRequest.remainingMillis(61000))
            assertEquals(1, releases)
            assertEquals(0L, ProductReadRequest.remainingMillis(62000))
            assertEquals(1, releases)
            ProductReadRequest.start(70000)
            ProductReadRequest.cancel()
            assertEquals(2, releases)
            assertEquals(0L, ProductReadRequest.remainingMillis(71000))
        } finally { ProductReadRequest.onCancelled = null; ProductReadRequest.cancel() }
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
