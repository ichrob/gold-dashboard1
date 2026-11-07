package ch.bob.degirocompanion

/** Classify only fixed visible error labels; never transmit screen text. */
internal object ConnectionErrorPolicy {
    fun detected(labels: List<String>): Boolean = labels.any {
        LocalWorkflow.normalize(it) in setOf("connection error", "verbindungsfehler", "keine internetverbindung")
    }
}
