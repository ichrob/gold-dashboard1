package ch.bob.degirocompanion

/** Memory only; a failed read replaces any old result. No screenshots or UI dumps. */
internal object ProductReadSession {
    private var result = ProductScreenEvidence.Result(message = "Noch keine Produktseite gelesen.")
    private var storedAt = 0L
    fun put(value: ProductScreenEvidence.Result, elapsed: Long) { result = value; storedAt = elapsed }
    fun get(elapsed: Long): ProductScreenEvidence.Result {
        if (elapsed < storedAt || elapsed - storedAt > 300000) clear()
        return result
    }
    fun clear() { result = ProductScreenEvidence.Result(message = "Kein gespeicherter Leseentwurf."); storedAt = 0 }
}
