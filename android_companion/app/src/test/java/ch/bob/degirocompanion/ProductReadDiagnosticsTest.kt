package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

class ProductReadDiagnosticsTest {
    @Test fun inlineQuoteNodesIdentifyProductScrollSurfaceWithoutUsingChartOrAccount() {
        for (row in listOf("Geld € 11,40", "Brief CHF 11,41", "Geld € 11,40 Brief € 11,41",
                "Zuletzt € 11,40 27/10/2026 17:32", "Kursdaten\nGeld € 11,40")) {
            assertEquals(row, 2, ProductScrollPolicy.evidence(row))
            val nodes = listOf(ProductScrollPolicy.Capability(true, true),
                ProductScrollPolicy.Capability(true, true, evidence = ProductScrollPolicy.evidence(row)))
            assertEquals(1, ProductScrollPolicy.select(nodes, true))
        }
        for (row in listOf("CHF 505,05", "€ 11,37", "Geld Vol. 25K", "Brief Vol. 25K",
                "1D 1W 1M", "Geld verdienen", "Geld € 11,40 kaufen"))
            assertEquals(row, 0, ProductScrollPolicy.evidence(row))
    }

    @Test fun choosesProductContainerAndNotChart() {
        val outer = ProductScrollPolicy.Capability(true, true, evidence = 3)
        val product = ProductScrollPolicy.Capability(true, true, ancestors = listOf(0), evidence = 3)
        val chart = ProductScrollPolicy.Capability(true, true, ancestors = listOf(0, 1))
        val nodes = listOf(outer, product, chart)
        assertEquals(1, ProductScrollPolicy.surface(nodes))
        assertEquals(1, ProductScrollPolicy.select(nodes, true))
        assertEquals(1, ProductScrollPolicy.select(nodes, false))
        // End of the product container must not fall back to the chart or wrapper.
        assertNull(ProductScrollPolicy.select(listOf(outer, product.copy(forward = false), chart), true))
    }
    @Test fun requiresCommonEvidenceAndRejectsUnrelatedTies() {
        val header = ProductScrollPolicy.Capability(true, true, evidence = 1)
        val quote = ProductScrollPolicy.Capability(true, true, evidence = 2)
        assertNull(ProductScrollPolicy.surface(listOf(header, quote)))
        assertNull(ProductScrollPolicy.surface(listOf(header, header)))
        assertNull(ProductScrollPolicy.surface(listOf(header.copy(evidence = 0), quote.copy(evidence = 0))))
        val outer = ProductScrollPolicy.Capability(true, true, evidence = 3)
        assertEquals(0, ProductScrollPolicy.surface(listOf(outer, header.copy(ancestors = listOf(0)), quote.copy(ancestors = listOf(0)))))
        assertNull(ProductScrollPolicy.surface(emptyList()))
        assertEquals(0, ProductScrollPolicy.select(listOf(header), true))
    }
    @Test fun evidenceDoesNotTreatChartOrAccountNumbersAsProductLabels() {
        assertEquals(1, ProductScrollPolicy.evidence("DE000FD0S0G4 · OTC"))
        assertEquals(0, ProductScrollPolicy.evidence("DE000FD0S0G5"))
        assertEquals(2, ProductScrollPolicy.evidence("Kursdaten"))
        assertEquals(2, ProductScrollPolicy.evidence("Brief"))
        assertEquals(0, ProductScrollPolicy.evidence("CHF 500,00"))
        assertEquals(0, ProductScrollPolicy.evidence("1D 1W 1M"))
    }

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
        ProductReadDiagnostics.rejected(ProductScreenEvidence.Reason.ISIN_MISSING)
        ProductReadDiagnostics.page(ProductPageReader.Cause.WAIT_PROTECTED)
        val report = ProductReadDiagnostics.report(2000)
        assertTrue(report.contains("NO_ROOT: 1"))
        assertTrue(report.contains("PAGE_WAIT_PROTECTED: 1"))
        assertTrue(report.contains("FIELD_ISIN_MISSING: 1"))
        assertTrue(report.contains("WINDOW_ROOT: 1"))
        assertFalse(report.contains("DE000"))
        assertFalse(ProductReadDiagnostics.report(301001).contains("NO_ROOT: 1"))
        assertFalse(ProductReadDiagnostics.report(301001).contains("FIELD_ISIN_MISSING"))
        assertFalse(ProductReadDiagnostics.report(301001).contains("PAGE_WAIT_PROTECTED"))
        ProductReadDiagnostics.reset(5000)
        ProductReadDiagnostics.record(ProductReadDiagnostics.Outcome.ERROR)
        assertFalse(ProductReadDiagnostics.report(4999).contains("ERROR: 1"))
        ProductReadDiagnostics.clear()
    }
}
