package ch.bob.degirocompanion

import android.app.Activity
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Build
import java.util.concurrent.atomic.AtomicInteger

/**
 * Fixed, opt-in bridge to Termux's RUN_COMMAND service.
 *
 * CHECK runs ONLY the pinned local Python --help invocation in the background,
 * with a private, one-shot callback reporting exit status. No stdout/stderr,
 * command string, file data, token or passphrase is read, logged or sent.
 *
 * LOCAL_ESCROW requires a separate local dialog. It remains foreground-only
 * and NEVER attaches a callback (even an exit-code callback) or remote input.
 */
internal object TermuxBridge {
    enum class Action { CHECK, LOCAL_ESCROW }

    const val PACKAGE = "com.termux"
    const val SERVICE = "com.termux.app.RunCommandService"
    const val PYTHON = "/data/data/com.termux/files/usr/bin/python"
    const val SCRIPT = "/data/data/com.termux/files/home/bob-sicher/bob_offline_key_escrow.py"
    const val OUTPUT = "/data/data/com.termux/files/home/bob-sicher/bob-archive-root.vault"
    const val CHECK_RESULT_ACTION = "ch.bob.degirocompanion.TERMUX_CHECK_RESULT"

    private const val PREFS = "termux_bridge_check"
    private const val RESULT_STATE = "state"
    private const val RESULT_AT = "at"
    private val requestNumbers = AtomicInteger(401)

    fun arguments(action: Action): Array<String> = when (action) {
        Action.CHECK -> arrayOf(SCRIPT, "--help")
        Action.LOCAL_ESCROW -> arrayOf(SCRIPT, "create", "--output", OUTPUT)
    }

    /** Pure, fixed-code classification. No Termux output or error message. */
    fun classifyCheckResult(err: Int?, exitCode: Int?): String = when {
        err == null || exitCode == null -> "TERMUX_RESULT_INCOMPLETE"
        err != Activity.RESULT_OK -> "TERMUX_INTERNAL_ERROR"
        exitCode == 0 -> "TERMUX_CHECK_EXECUTED"
        else -> "TERMUX_CHECK_FAILED"
    }

    fun recordCheck(context: Context, value: String) {
        val allowed = setOf("TERMUX_CHECK_PENDING", "TERMUX_CHECK_EXECUTED",
            "TERMUX_CHECK_FAILED", "TERMUX_RESULT_INCOMPLETE",
            "TERMUX_INTERNAL_ERROR", "TERMUX_NOT_INSTALLED",
            "TERMUX_UNAVAILABLE", "TERMUX_PERMISSION_REQUIRED",
            "TERMUX_START_RESTRICTED")
        val state = if (value in allowed) value else "TERMUX_UNAVAILABLE"
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
            .putString(RESULT_STATE, state)
            .putLong(RESULT_AT, System.currentTimeMillis())
            .apply()
    }

    fun checkStatus(context: Context): String {
        val p = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val state = p.getString(RESULT_STATE, "") ?: ""
        val age = System.currentTimeMillis() - p.getLong(RESULT_AT, 0L)
        return if (state == "TERMUX_CHECK_PENDING" && age > 15000L)
            "TERMUX_RESULT_NOT_RECEIVED" else state
    }

    fun displayStatus(context: Context): String = when (checkStatus(context)) {
        "TERMUX_CHECK_EXECUTED" ->
            "Termux hat den festen Python-Test mit Exitcode 0 abgeschlossen. Keine Schlüssel verarbeitet."
        "TERMUX_CHECK_PENDING" -> "Termux-Test gestartet; Ausführungsquittung steht aus."
        "TERMUX_RESULT_NOT_RECEIVED" ->
            "Noch keine Ausführungsquittung aus Termux. Verbindung nicht bestätigt."
        "TERMUX_CHECK_FAILED" -> "Termux hat den Test mit Fehler beendet. Keine Schlüssel verarbeitet."
        "TERMUX_INTERNAL_ERROR" -> "Termux meldet einen Start-/Sitzungsfehler."
        "TERMUX_RESULT_INCOMPLETE" -> "Termux-Rückmeldung unvollständig."
        "TERMUX_NOT_INSTALLED" -> "Termux auf diesem Gerät nicht gefunden."
        "TERMUX_PERMISSION_REQUIRED" ->
            "Android: Bob Handy → Berechtigungen → Termux-Befehle erlauben."
        "TERMUX_START_RESTRICTED" -> "Android hat den Start eingeschränkt."
        "TERMUX_UNAVAILABLE" -> "Termux ist nicht erreichbar."
        else -> "Termux-Verbindung noch nicht geprüft."
    }

    fun launch(context: Context, action: Action): String {
        if (context.packageManager.getLaunchIntentForPackage(PACKAGE) == null) {
            if (action == Action.CHECK) recordCheck(context, "TERMUX_NOT_INSTALLED")
            return "TERMUX_NOT_INSTALLED"
        }
        val isCheck = action == Action.CHECK
        val request = Intent("com.termux.RUN_COMMAND").apply {
            setClassName(PACKAGE, SERVICE)
            putExtra("com.termux.RUN_COMMAND_PATH", PYTHON)
            putExtra("com.termux.RUN_COMMAND_ARGUMENTS", arguments(action))
            putExtra("com.termux.RUN_COMMAND_WORKDIR",
                "/data/data/com.termux/files/home")
            putExtra("com.termux.RUN_COMMAND_BACKGROUND", isCheck)
            if (!isCheck) {
                putExtra("com.termux.RUN_COMMAND_SESSION_ACTION", "0")
            } else {
                // Termux >= 0.109 returns only to this non-exported receiver.
                // Never attach a callback to the secret-handling operation.
                val callback = Intent(context, TermuxCheckResultReceiver::class.java)
                    .setAction(CHECK_RESULT_ACTION)
                val flags = PendingIntent.FLAG_ONE_SHOT or
                    (if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S)
                        PendingIntent.FLAG_MUTABLE else 0)
                val pending = PendingIntent.getBroadcast(context,
                    requestNumbers.incrementAndGet(), callback, flags)
                putExtra("com.termux.RUN_COMMAND_PENDING_INTENT", pending)
            }
        }
        if (isCheck) recordCheck(context, "TERMUX_CHECK_PENDING")
        val result = try {
            if (context.startService(request) == null)
                "TERMUX_UNAVAILABLE" else "TERMUX_REQUESTED"
        } catch (_: SecurityException) {
            "TERMUX_PERMISSION_REQUIRED"
        } catch (_: IllegalStateException) {
            "TERMUX_START_RESTRICTED"
        } catch (_: RuntimeException) {
            "TERMUX_UNAVAILABLE"
        }
        if (isCheck && result != "TERMUX_REQUESTED") recordCheck(context, result)
        return result
    }
}
