package ch.bob.degirocompanion

import android.content.Context
import android.os.SystemClock

/** Owner-started 4h / 8h monitoring window.
 * Server-side Gold monitoring is independent of this phone-side preference.
 * Only the existing explicitly started, at-most-15-minute read can touch DEGIRO.
 */
internal object BobWorkMode {
    private const val PREFS = "bob_work_mode_v1"
    private const val HOURS = "hours"
    private const val START_WALL = "start_wall"
    private const val START_ELAPSED = "start_elapsed"

    data class State(val hours: Int, val remainingMillis: Long) {
        val active: Boolean get() = remainingMillis > 0
    }

    fun start(c: Context, hours: Int): State {
        BobWorkModePolicy.duration(hours)
        val wall = System.currentTimeMillis()
        val elapsed = SystemClock.elapsedRealtime()
        check(c.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
            .putInt(HOURS, hours)
            .putLong(START_WALL, wall)
            .putLong(START_ELAPSED, elapsed)
            .commit()) { "Bob-Arbeitsmodus konnte nicht gespeichert werden." }
        return State(hours, BobWorkModePolicy.duration(hours))
    }

    fun state(c: Context, wall: Long = System.currentTimeMillis(),
              elapsed: Long = SystemClock.elapsedRealtime()): State {
        val p = c.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val hours = p.getInt(HOURS, 0)
        if(hours != 4 && hours != 8) return State(0, 0)
        return State(hours, BobWorkModePolicy.remaining(
            p.getLong(START_WALL, 0), p.getLong(START_ELAPSED, -1),
            hours, wall, elapsed))
    }

    fun stop(c: Context) {
        c.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().clear().commit()
    }

    fun status(c: Context): String {
        val s = state(c)
        if(!s.active) return "Arbeitsmodus aus. Die serverseitige Marktüberwachung läuft unabhängig davon."
        val minutes = BobWorkModePolicy.remainingMinutes(s.remainingMillis)
        return "Bob-Arbeitsmodus: ${s.hours} Stunden gewählt · noch ${minutes / 60} h ${minutes % 60} min. " +
            "Serverüberwachung ohne Display; DEGIRO nur bei entsperrtem Samsung in einer " +
            "separaten, höchstens 15-minütigen Lesesitzung. Keine automatische Gerätesperren-Entsperrung."
    }
}
