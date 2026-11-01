package ch.bob.degirocompanion

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class SelectiveDetailPlanTest {
    private val first = "DE000FB0CVV9"
    private val second = "DE000SQ02JQ6"
    private fun entry(isin: String, vararg missing: String) =
        JSONObject().put("isin", isin).put("missingFields", JSONArray(missing.toList()))

    @Test fun onlyMissingFieldsInServerOrderAreAccepted() {
        val values=listOf(first,second)
        val plan=JSONArray().put(entry(first,"Geld","Anzeigezeit"))
            .put(entry(second,"KO-Schwelle","Bv"))
        val read=SelectiveDetailPlan.parse(plan,values)!!
        assertEquals(values,read.map { it.isin })
        assertEquals(listOf("Geld","Anzeigezeit"),read[0].missingFields)
        assertEquals(listOf("KO-Schwelle","Bv"),read[1].missingFields)
        assertEquals(emptyList<SelectiveDetailPlan.Entry>(),
            SelectiveDetailPlan.parse(JSONArray(),emptyList()))
    }

    @Test fun completeOrTamperedProductsNeverCauseAnExtraRead() {
        val values=listOf(first,second)
        val good=JSONArray().put(entry(first,"Hebel")).put(entry(second,"Währung"))
        assertNull(SelectiveDetailPlan.parse(null,values))
        assertNull(SelectiveDetailPlan.parse(good,values.reversed()))
        assertNull(SelectiveDetailPlan.parse(good,listOf(first,first)))
        assertNull(SelectiveDetailPlan.parse(JSONArray().put(entry(first,"Hebel")),values))
        assertNull(SelectiveDetailPlan.parse(JSONArray().put(entry(first,"Hebel")).put(entry(second)),values))
        assertNull(SelectiveDetailPlan.parse(JSONArray().put(entry(first,"Hebel")).put(entry(second,"Passwort")),values))
        assertNull(SelectiveDetailPlan.parse(JSONArray().put(entry(first,"Hebel","Hebel")).put(entry(second,"Geld")),values))
        assertNull(SelectiveDetailPlan.parse(JSONArray().put(entry(first)).put(entry(second,"Brief")),values))
        assertNull(SelectiveDetailPlan.parse(JSONArray().put(entry(first,"Geld").put("order","BUY"))
            .put(entry(second,"Brief")),values))
    }
}
