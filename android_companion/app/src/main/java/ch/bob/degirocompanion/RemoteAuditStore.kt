package ch.bob.degirocompanion

import android.content.Context
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * Minimal local evidence log. Events only: NO request bodies, pairing tokens,
 * screenshots, utterances, clipboard content, ISINs or broker/account data.
 * Kept in the app-private storage; no automatic upload.
 */
internal class RemoteAuditStore(context: Context) {
    private val prefs = context.getSharedPreferences("bob_remote_audit_v1", Context.MODE_PRIVATE)
    private val key = "events"

    fun append(nowWallMs: Long, event: RemoteAuditEvent, task: PhoneTask?) {
        val line = listOf(nowWallMs.coerceAtLeast(0), event.name, task?.name ?: "-").joinToString("|")
        val current = prefs.getString(key, "").orEmpty().lineSequence()
            .filter { it.isNotBlank() }.takeLastSafe(79)
        prefs.edit().putString(key, (current + line).takeLast(80).joinToString("\n")).apply()
    }

    fun summary(limit: Int = 12): String {
        val formatter = SimpleDateFormat("dd.MM. HH:mm:ss", Locale.GERMAN)
        return prefs.getString(key, "").orEmpty().lineSequence()
            .filter { it.isNotBlank() }.takeLastSafe(limit.coerceIn(1, 80))
            .mapNotNull { line ->
                val parts = line.split('|')
                if (parts.size != 3) return@mapNotNull null
                val timestamp = parts[0].toLongOrNull() ?: return@mapNotNull null
                val code = RemoteAuditEvent.entries.firstOrNull { it.name == parts[1] }
                    ?: return@mapNotNull null
                val action = if (parts[2] == "-") "-" else
                    PhoneTask.entries.firstOrNull { it.name == parts[2] }?.name
                        ?: return@mapNotNull null
                formatter.format(Date(timestamp)) + " · " + code.name + " · " + action
            }.joinToString("\n").ifBlank { "Noch keine Kopplungsereignisse." }
    }

    private fun <T> Sequence<T>.takeLastSafe(count: Int): List<T> = toList().takeLast(count)
}
