package ch.bob.degirocompanion

import android.content.Context
import android.graphics.Bitmap
import org.json.JSONArray
import org.json.JSONObject

internal data class LearnedSymbol(val name: String, val expected: String, val pattern: SymbolPattern, val verifiedAt: Long = 0) {
    val target get() = "Symbol: $name"
}
/** Only the local owner learning dialog writes this bounded, app-scoped store. */
internal object WorkflowSymbols {
    private fun prefs(c: Context) = c.getSharedPreferences("workflow_symbols_v1", Context.MODE_PRIVATE)
    private fun key(app: String, name: String) = "$app:${LocalWorkflow.normalize(name)}"
    fun gray(bitmap: Bitmap): IntArray {
        val pixels = IntArray(bitmap.width * bitmap.height)
        bitmap.getPixels(pixels, 0, bitmap.width, 0, 0, bitmap.width, bitmap.height)
        return pixels.map { ((it shr 16 and 255) * 77 + (it shr 8 and 255) * 150 + (it and 255) * 29) shr 8 }.toIntArray()
    }
    fun list(c: Context, app: String): List<LearnedSymbol> = prefs(c).all.entries.filter { it.key.startsWith("$app:") }.mapNotNull { entry ->
        runCatching {
            val j = JSONObject(entry.value as String)
            require(j.getString("app") == app)
            val a = j.getJSONArray("pixels"); require(a.length() == 256)
            val pattern = SymbolPattern(IntArray(256) { a.getInt(it) }, j.getDouble("width"), j.getDouble("height"), j.getDouble("aspect"))
            require(WorkflowSymbolMatch.distinctive(pattern.pixels) && pattern.widthRatio in .001.. .5 && pattern.heightRatio in .001.. .5 && pattern.aspect in .1..10.0)
            val name = j.getString("name"); val expected = j.getString("expected")
            require(WorkflowComposer.validText(name) && WorkflowComposer.validText(expected))
            LearnedSymbol(name, expected, pattern, j.optLong("verifiedAt"))
        }.getOrNull()
    }.sortedBy { it.name }.take(20)
    fun find(c: Context, app: String, target: String) = list(c, app).singleOrNull { it.target == target }
    fun save(c: Context, app: String, symbol: LearnedSymbol): Boolean {
        if (!LocalWorkflow.allowedApp(app) || !WorkflowComposer.validText(symbol.name) || symbol.name.length > 60 ||
            !WorkflowComposer.validText(symbol.expected) || !WorkflowSymbolMatch.distinctive(symbol.pattern.pixels)) return false
        val p = prefs(c); val key = key(app, symbol.name)
        if (!p.contains(key) && p.all.size >= 20) return false
        val j = JSONObject().put("app", app).put("name", symbol.name).put("expected", symbol.expected)
            .put("pixels", JSONArray(symbol.pattern.pixels.toList())).put("width", symbol.pattern.widthRatio)
            .put("height", symbol.pattern.heightRatio).put("aspect", symbol.pattern.aspect).put("verifiedAt", symbol.verifiedAt)
        return p.edit().putString(key, j.toString()).commit()
    }
    fun forget(c: Context, app: String, name: String) = prefs(c).edit().remove(key(app, name)).commit()
    fun plan(c: Context, app: String, goal: String): List<WorkflowStep>? {
        val normalized = LocalWorkflow.normalize(goal)
        val symbol = list(c, app).singleOrNull { s -> listOf(s.name, "Tippe auf ${s.name}", "Klicke auf ${s.name}", "Öffne ${s.name}").any { LocalWorkflow.normalize(it) == normalized } } ?: return null
        return listOf(WorkflowStep(WorkflowAction.CLICK, symbol.target, expected = symbol.expected))
    }
    fun verified(c: Context, app: String, target: String) {
        find(c, app, target)?.let { save(c, app, it.copy(verifiedAt = System.currentTimeMillis())) }
    }
}
