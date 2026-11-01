package ch.bob.degirocompanion

import org.json.JSONArray

/** Validate the server's exact per-product missing-field plan. Read-only only. */
internal object SelectiveDetailPlan {
    val fields = setOf("Geld", "Brief", "Anzeigezeit", "Hebel",
        "KO-Schwelle", "Basispreis", "Bv", "Währung")
    data class Entry(val isin: String, val missingFields: List<String>)

    /** Pure policy used by local JVM tests without Android's JSON stubs. */
    fun validate(entries: List<Entry>, orderedIsins: List<String>): List<Entry>? {
        if (entries.size != orderedIsins.size || orderedIsins.size > 10 ||
            orderedIsins.distinct() != orderedIsins ||
            orderedIsins.any { !SeriesEvidence.validIsin(it) }) return null
        for (i in orderedIsins.indices) {
            val e = entries[i]
            if (e.isin != orderedIsins[i] || e.missingFields.size !in 1..fields.size ||
                e.missingFields.any { it !in fields } ||
                e.missingFields.distinct() != e.missingFields) return null
        }
        return entries
    }

    fun parse(plan: JSONArray?, orderedIsins: List<String>): List<Entry>? {
        if (plan == null || plan.length() != orderedIsins.size) return null
        val entries = mutableListOf<Entry>()
        for (i in orderedIsins.indices) {
            val item = plan.optJSONObject(i) ?: return null
            if (item.length() != 2 || !item.has("isin") || !item.has("missingFields")) return null
            val values = item.optJSONArray("missingFields") ?: return null
            entries += Entry(item.optString("isin"),
                (0 until values.length()).map { values.optString(it) })
        }
        return validate(entries, orderedIsins)
    }
}
