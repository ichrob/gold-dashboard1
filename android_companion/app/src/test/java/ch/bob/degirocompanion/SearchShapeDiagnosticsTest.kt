package ch.bob.degirocompanion
import org.junit.Assert.*
import org.junit.Test
class SearchShapeDiagnosticsTest {
    @Test fun exportsOnlyFixedFlagsAndClearsThem() {
        ProductReadDiagnostics.reset(1000)
        ProductReadDiagnostics.searchShape(ProductReadDiagnostics.SearchSource.INPUT_DESCRIPTION,
            "Mit Namen, ISIN oder Symbol suchen · Bearbeitungsfeld · private-secret-123")
        ProductReadDiagnostics.searchShape(ProductReadDiagnostics.SearchSource.INPUT_TEXT,"CHF 505,00")
        val report=ProductReadDiagnostics.report(1001)
        assertTrue(report.contains("SEARCH_SHAPE_INPUT_DESCRIPTION_PROMPT_WORDS: 1"))
        assertFalse(report.contains("EXACT_PROMPT"))
        for(secret in listOf("private-secret", "505,00", "Bearbeitungsfeld", "Mit Namen")) assertFalse(report.contains(secret))
        ProductReadDiagnostics.reset(2000)
        assertFalse(ProductReadDiagnostics.report(2001).contains("SEARCH_SHAPE_"))
    }
    @Test fun distinguishesExactPromptFromGenericMetadata() {
        ProductReadDiagnostics.reset(1000)
        ProductReadDiagnostics.searchShape(ProductReadDiagnostics.SearchSource.INPUT_HINT,"Mit Namen, ISIN oder Symbol suchen")
        ProductReadDiagnostics.searchShape(ProductReadDiagnostics.SearchSource.INPUT_ID,"generic-input")
        val report=ProductReadDiagnostics.report(1001)
        assertTrue(report.contains("SEARCH_SHAPE_INPUT_HINT_EXACT_PROMPT: 1"))
        assertTrue(report.contains("SEARCH_SHAPE_INPUT_ID_PRESENT: 1"))
        assertFalse(report.contains("SEARCH_SHAPE_INPUT_ID_SEARCH_WORD"))
        assertFalse(ProductReadDiagnostics.report(301001).contains("SEARCH_SHAPE_"))
    }
}
