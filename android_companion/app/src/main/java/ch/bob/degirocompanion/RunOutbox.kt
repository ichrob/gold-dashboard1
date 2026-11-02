package ch.bob.degirocompanion

/** Pure transitions for durable, independently acknowledged reading runs. */
internal object RunOutbox {
    const val CURRENT = "outbox"
    const val PREFIX = "saved_run_"
    /** Local-only generation for detecting new evidence in the durable queue.
     * The digest is never sent to Bob or exposed in logs. */
    fun generation(entries: Map<String,String>): String {
        val digest=java.security.MessageDigest.getInstance("SHA-256")
        entries.toSortedMap().forEach { (key,value) ->
            fun add(s:String) {
                val bytes=s.toByteArray(Charsets.UTF_8)
                digest.update(java.nio.ByteBuffer.allocate(4).putInt(bytes.size).array())
                digest.update(bytes)
            }
            add(key);add(value)
        }
        return digest.digest().joinToString("") { "%02x".format(it.toInt() and 255) }
    }
    fun candidateKeys(entries: Map<String, String>): List<String> =
        (if (CURRENT in entries) listOf(CURRENT) else emptyList()) +
            entries.keys.filter { it.startsWith(PREFIX) }.sorted()
    fun pendingKey(entries: Map<String, String>): String? = candidateKeys(entries).firstOrNull()
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
