package ch.bob.degirocompanion

import org.json.JSONArray

/** Validate the server's exact per-product missing-field plan. Read-only only. */
internal object SelectiveDetailPlan {
    val fields = setOf("Geld", "Brief", "Anzeigezeit", "Hebel",
        "KO-Schwelle", "Basispreis", "Bv", "Währung")
    data class Entry(val isin: String, val missingFields: List<String>)

    fun parse(plan: JSONArray?, orderedIsins: List<String>): List<Entry>? {
        if (plan == null || plan.length() != orderedIsins.size ||
            orderedIsins.size > 10 || orderedIsins.distinct() != orderedIsins ||
            orderedIsins.any { !SeriesEvidence.validIsin(it) }) return null
        val entries = mutableListOf<Entry>()
        for (index in orderedIsins.indices) {
            val item = plan.optJSONObject(index) ?: return null
            if (item.length() != 2 || !item.has("isin") || !item.has("missingFields") ||
                item.optString("isin") != orderedIsins[index]) return null
            val values = item.optJSONArray("missingFields") ?: return null
            if (values.length() !in 1..fields.size) return null
            val missing = (0 until values.length()).map { values.optString(it) }
            if (missing.any { it !in fields } || missing.distinct() != missing) return null
            entries += Entry(orderedIsins[index], missing)
        }
        return entries
    }
}
