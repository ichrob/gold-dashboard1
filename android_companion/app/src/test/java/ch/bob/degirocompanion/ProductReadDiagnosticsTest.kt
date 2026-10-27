package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

class ProductReadDiagnosticsTest {
    @Test fun onlyOneActiveFocusedApplicationWindowMayBeSelected() {
        val allowed = ProductWindowPolicy.Window(true, true, true)
        assertEquals(0, ProductWindowPolicy.select(listOf(allowed)))
        assertNull(ProductWindowPolicy.select(emptyList()))
        assertNull(ProductWindowPolicy.select(listOf(allowed, allowed)))
        assertNull(ProductWindowPolicy.select(listOf(ProductWindowPolicy.Window(false, true, true))))
        assertNull(ProductWindowPolicy.select(listOf(ProductWindowPolicy.Window(true, false, true))))
        assertNull(ProductWindowPolicy.select(listOf(ProductWindowPolicy.Window(true, true, false))))
        assertEquals(1, ProductWindowPolicy.select(listOf(ProductWindowPolicy.Window(false, false, true), allowed)))
    }
    @Test fun reportsOnlyFixedCountersAndExpires() {
        ProductReadDiagnostics.reset(1000)
        ProductReadDiagnostics.record(ProductReadDiagnostics.Outcome.NO_ROOT)
        ProductReadDiagnostics.record(ProductReadDiagnostics.Outcome.WINDOW_ROOT)
        val report = ProductReadDiagnostics.report(2000)
        assertTrue(report.contains("NO_ROOT: 1"))
        assertTrue(report.contains("WINDOW_ROOT: 1"))
        assertFalse(report.contains("ISIN"))
        assertFalse(ProductReadDiagnostics.report(301001).contains("NO_ROOT: 1"))
        ProductReadDiagnostics.reset(5000)
        ProductReadDiagnostics.record(ProductReadDiagnostics.Outcome.ERROR)
        assertFalse(ProductReadDiagnostics.report(4999).contains("ERROR: 1"))
        ProductReadDiagnostics.clear()
    }
}
