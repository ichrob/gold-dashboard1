package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

/** Plain Kotlin policy tests: no Android SDK JSONObject mocks. */
class SelectiveDetailPlanTest {
    private val first = "DE000FB0CVV9"
    private val second = "DE000SQ02JQ6"
    private fun entry(isin: String, vararg missing: String) =
        SelectiveDetailPlan.Entry(isin, missing.toList())

    @Test fun onlyStillMissingFieldsInServerOrderAreAccepted() {
        val values=listOf(first,second)
        val entries=listOf(entry(first,"Geld","Anzeigezeit"),entry(second,"KO-Schwelle","Bv"))
        val parsed=SelectiveDetailPlan.validate(entries,values)!!
        assertEquals(values,parsed.map { it.isin })
        assertEquals(listOf("Geld","Anzeigezeit"),parsed[0].missingFields)
        assertEquals(listOf("KO-Schwelle","Bv"),parsed[1].missingFields)
        assertEquals(emptyList<SelectiveDetailPlan.Entry>(),
            SelectiveDetailPlan.validate(emptyList(),emptyList()))
    }

    @Test fun completeOrTamperedProductsNeverCauseAnExtraRead() {
        val values=listOf(first,second)
        val good=listOf(entry(first,"Hebel"),entry(second,"Währung"))
        assertNull(SelectiveDetailPlan.validate(good,values.reversed()))
        assertNull(SelectiveDetailPlan.validate(good,listOf(first,first)))
        assertNull(SelectiveDetailPlan.validate(listOf(entry(first,"Hebel")),values))
        assertNull(SelectiveDetailPlan.validate(listOf(entry(first,"Hebel"),entry(second,"Passwort")),values))
        assertNull(SelectiveDetailPlan.validate(listOf(entry(first,"Hebel","Hebel"),entry(second,"Geld")),values))
        assertNull(SelectiveDetailPlan.validate(listOf(entry(first),entry(second,"Brief")),values))
        assertNull(SelectiveDetailPlan.validate(listOf(entry(first,"Geld"),entry(first,"Brief")),values))
    }
}
