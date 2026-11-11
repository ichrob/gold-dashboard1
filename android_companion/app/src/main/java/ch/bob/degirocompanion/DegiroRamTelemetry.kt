package ch.bob.degirocompanion

import android.content.Context
import android.os.Debug
import android.os.SystemClock
import org.json.JSONArray
import org.json.JSONObject
import java.time.Instant
import java.util.concurrent.Executors
import java.util.concurrent.ScheduledFuture
import java.util.concurrent.TimeUnit

/**
 * Samples only Bob Handy's own proportional-set-size RAM (PSS), not DEGIRO or
 * the entire device. The sampled peak is a lower bound on any instantaneous
 * peak. Runs only while a user-authorized DEGIRO reading request is active.
 */
internal object DegiroRamTelemetry {
    private const val PREFS = "degiro_ram_v1"
    private const val HISTORY = "recent_runs"
    private const val LIMIT = 12
    private const val INTERVAL_SEC = 3L
    private val thread = Executors.newSingleThreadScheduledExecutor { job ->
        Thread(job, "bob-degiro-ram").apply { isDaemon = true }
    }
    private val lock = Any()
    private data class Run(val phase: String, val startedAt: String,
                           val startedElapsed: Long, val samples: RamUsageSamples = RamUsageSamples())
    private var current: Run? = null
    private var scheduled: ScheduledFuture<*>? = null

    fun start(context: Context) {
        val app = context.applicationContext
        val phase = when {
            MorningReadRun.running -> "PRODUCT_DETAILS"
            GoldSearchRun.running -> "GOLD_LIST"
            else -> "SINGLE_PAGE"
        }
        val run = Run(phase, Instant.now().toString(), SystemClock.elapsedRealtime())
        synchronized(lock) {
            scheduled?.cancel(false)
            current?.let { prior -> thread.execute { sample(prior); store(app, prior, "REPLACED") } }
            current = run
            scheduled = thread.scheduleAtFixedRate(
                { sample(run) }, 0L, INTERVAL_SEC, TimeUnit.SECONDS)
        }
    }

    fun finish(context: Context, reason: String) {
        val run = synchronized(lock) {
            scheduled?.cancel(false)
            scheduled = null
            val completed = current
            current = null
            completed
        } ?: return
        val app = context.applicationContext
        thread.execute { sample(run); store(app, run, reason) }
    }

    private fun sample(run: Run) {
        // Neither call reads DEGIRO, screen pixels, other apps or credentials.
        val pssKiB = runCatching { Debug.getPss() }.getOrDefault(-1L)
        val runtime = Runtime.getRuntime()
        val heapKiB = ((runtime.totalMemory() - runtime.freeMemory()).coerceAtLeast(0L)) / 1024L
        run.samples.record(pssKiB, heapKiB)
    }

    private fun jsonMiB(kib: Long): Any = RamUsageSamples.toMiB(kib) ?: JSONObject.NULL

    private fun store(context: Context, run: Run, reason: String) {
        val samples = run.samples
        val record = JSONObject()
            .put("phase", run.phase)
            .put("startedAt", run.startedAt)
            .put("finishedAt", Instant.now().toString())
            .put("durationSec", ((SystemClock.elapsedRealtime() - run.startedElapsed).coerceAtLeast(0L)) / 1000L)
            .put("endReason", reason)
            .put("sampleIntervalSec", INTERVAL_SEC)
            .put("sampleCount", samples.sampleCount)
            .put("startPssMiB", jsonMiB(samples.startPssKiB))
            .put("sampledPeakPssMiB", jsonMiB(samples.peakPssKiB))
            .put("endPssMiB", jsonMiB(samples.endPssKiB))
            .put("sampledPeakJavaHeapMiB", jsonMiB(samples.peakHeapKiB))
        val p = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val old = runCatching { JSONArray(p.getString(HISTORY, "[]")) }.getOrElse { JSONArray() }
        val recent = JSONArray()
        for (i in (old.length() - LIMIT + 1).coerceAtLeast(0) until old.length()) {
            recent.put(old.getJSONObject(i))
        }
        recent.put(record)
        if (p.edit().putString(HISTORY, recent.toString()).commit()) {
            // Existing opt-in diagnostics may upload a bounded, anonymous summary.
            PhoneDiagnostics.queue(context)
        }
    }

    fun latest(context: Context): JSONObject? {
        val raw = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getString(HISTORY, "[]")
        return runCatching {
            val entries = JSONArray(raw)
            if (entries.length() > 0) entries.getJSONObject(entries.length() - 1) else null
        }.getOrNull()
    }

    fun display(context: Context): String {
        val recent = latest(context) ?: return "RAM-Messung: noch kein abgeschlossener Leselauf."
        fun value(name: String) =
            if (recent.isNull(name)) "nicht gemessen" else "${recent.optDouble(name)} MiB"
        return "Bob-Handy-RAM (${recent.optString("phase")}; ${recent.optInt("sampleCount")} Stichproben): " +
            "Start ${value("startPssMiB")} · Spitze ${value("sampledPeakPssMiB")} · " +
            "Ende ${value("endPssMiB")}. Stichproben-Spitze, nicht Gesamtgeräte-RAM."
    }
}
