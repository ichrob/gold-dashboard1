package ch.bob.degirocompanion

/** Pure transitions for durable, independently acknowledged reading runs. */
internal object RunOutbox {
    const val CURRENT = "outbox"
    const val PREFIX = "saved_run_"
    fun pendingKey(entries: Map<String, String>): String? =
        if (CURRENT in entries) CURRENT else entries.keys.filter { it.startsWith(PREFIX) }.sorted().firstOrNull()
    fun start(entries: Map<String, String>, raw: String, archiveKey: String): Map<String, String> {
        require(archiveKey.startsWith(PREFIX) && archiveKey !in entries)
        return entries.toMutableMap().apply {
            entries[CURRENT]?.let { put(archiveKey, it) }
            put(CURRENT, raw)
        }
    }
    fun acknowledge(entries: Map<String, String>, key: String, expected: String, running: Boolean): Map<String, String>? {
        if (entries[key] != expected || (key == CURRENT && running)) return null
        return entries - key
    }
}
