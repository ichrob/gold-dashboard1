package ch.bob.degirocompanion

import java.time.Instant

/** Only select the newest bounded diagnostic code; never inspect or export text. */
internal object PhoneDiagnosticRecency {
    data class Event(val code:String,val at:String)
    fun latest(vararg events:Event?):Event? =
        events.filterNotNull().mapNotNull { e ->
            runCatching { Instant.parse(e.at) to e }.getOrNull()
        }.maxByOrNull { it.first }?.second
}
