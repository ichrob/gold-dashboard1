package ch.bob.degirocompanion

import android.app.KeyguardManager
import android.content.Context
import android.os.Handler
import android.os.Looper
import android.os.PowerManager
import android.os.SystemClock
import java.util.concurrent.Executors

/** A foreground-device, owner-started, bounded visual reading readiness while
 * the SAME single Bob real-trade journal record is active. Never navigates,
 * enters PIN, trades, or keeps Android unlocked after the power button is used.
 * A process death releases the wake lock. Remote trading consent is unchanged.
 */
internal object BobTradeDimMode {
    private val handler = Handler(Looper.getMainLooper())
    private val worker = Executors.newSingleThreadExecutor()
    private var generation = 0
    private var checking = false
    private var active = false
    private var startedAt = 0L
    private var linkedTag: String? = null
    private var lease: PowerManager.WakeLock? = null
    private var label = "Trade-Lesemodus aus."
    val running get() = active
    val status get() = label

    private fun unlocked(c: Context): Boolean {
        val power = c.getSystemService(Context.POWER_SERVICE) as PowerManager
        val keyguard = c.getSystemService(Context.KEYGUARD_SERVICE) as KeyguardManager
        return power.isInteractive && !keyguard.isKeyguardLocked && !keyguard.isDeviceLocked
    }

    @Suppress("DEPRECATION")
    private fun renew(c: Context): Boolean {
        if(!unlocked(c)) return false
        return runCatching {
            val power = c.getSystemService(Context.POWER_SERVICE) as PowerManager
            lease?.let { if(it.isHeld)it.release() }
            lease = power.newWakeLock(PowerManager.SCREEN_DIM_WAKE_LOCK, "Bob:OwnerTradeDim").also {
                it.setReferenceCounted(false)
                it.acquire(BobTradeDimPolicy.SCREEN_LEASE_MILLIS)
            }
            true
        }.getOrDefault(false)
    }

    fun stop(reason: String = "Durch STOPP beendet.") {
        generation++
        checking = false
        active = false
        linkedTag = null
        startedAt = 0L
        lease?.let { if(it.isHeld)it.release() }
        lease = null
        label = "Trade-Lesemodus aus · $reason"
    }

    fun start(context: Context, onStatus: (String) -> Unit) {
        if(active || checking) {
            onStatus(label)
            return
        }
        val c = context.applicationContext
        if(!unlocked(c) || !PhoneDiagnostics.paired(c) || !ProductReadDiagnostics.connected) {
            onStatus("Trade-Lesemodus nicht gestartet: Samsung entsperren und Bob-Lesedienst/Diagnose verbinden.")
            return
        }
        checking = true
        generation++
        val ticket = generation
        label = "Prüfe einen eindeutig aktiven Trade auf Bobs Server."
        onStatus(label)
        worker.execute {
            val receipt = runCatching { PhoneDiagnostics.tradeMonitorStatus(c) }.getOrNull()
            handler.post {
                if(ticket != generation) return@post
                checking = false
                val now = System.currentTimeMillis() / 1000
                val state = receipt?.optString("state").orEmpty()
                val tag = receipt?.optString("tradeTag").orEmpty()
                val checked = receipt?.optLong("checkedAt", 0) ?: 0L
                if(!unlocked(c) || !BobTradeDimPolicy.validReceipt(state,tag,checked,now)) {
                    label = "Trade-Lesemodus nicht gestartet: kein eindeutig aktiver, aktuell bestätigter Bob-Trade."
                    onStatus(label)
                    return@post
                }
                linkedTag = tag
                active = true
                startedAt = SystemClock.elapsedRealtime()
                if(!renew(c)) {
                    stop("Android konnte die Bildschirm-Wachhaltung nicht aktivieren.")
                    onStatus(label)
                    return@post
                }
                label = "Trade-Lesemodus aktiv: Samsung entsperrt und Bildschirm wach. " +
                    "Abschaltung bei Bob-Trade-Ende, STOPP, Gerätesperre, Verbindungsfehler oder nach 8 Stunden."
                onStatus(label)
                handler.postDelayed({ poll(c,ticket) }, BobTradeDimPolicy.POLL_MILLIS)
            }
        }
    }

    private fun poll(c: Context, ticket: Int) {
        if(ticket != generation || !active) return
        if(!BobTradeDimPolicy.eligible(active,
                SystemClock.elapsedRealtime() - startedAt,
                (c.getSystemService(Context.POWER_SERVICE) as PowerManager).isInteractive,
                !unlocked(c), PhoneDiagnostics.paired(c), linkedTag != null)) {
            stop("Trade-Lesebereitschaft abgelaufen oder Samsung gesperrt.")
            return
        }
        worker.execute {
            val receipt = runCatching { PhoneDiagnostics.tradeMonitorStatus(c) }.getOrNull()
            handler.post {
                if(ticket != generation || !active) return@post
                val now = System.currentTimeMillis()/1000
                val tag = receipt?.optString("tradeTag").orEmpty()
                val valid = BobTradeDimPolicy.validReceipt(receipt?.optString("state").orEmpty(),
                    tag, receipt?.optLong("checkedAt",0) ?: 0L, now)
                if(!valid || tag != linkedTag) {
                    stop("Bob meldet keinen bestätigten, unveränderten aktiven Trade oder die Verbindung ist unterbrochen.")
                    return@post
                }
                if(!renew(c)) {
                    stop("Bildschirm gesperrt oder Android-Wachhaltung abgelehnt.")
                    return@post
                }
                handler.postDelayed({ poll(c,ticket) }, BobTradeDimPolicy.POLL_MILLIS)
            }
        }
    }
}
