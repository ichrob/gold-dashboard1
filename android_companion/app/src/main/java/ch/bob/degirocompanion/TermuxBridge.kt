package ch.bob.degirocompanion

import android.app.Activity
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Build
import java.util.concurrent.atomic.AtomicInteger
import java.io.ByteArrayOutputStream
import java.security.MessageDigest
import java.util.Base64
import java.util.zip.GZIPOutputStream

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

    // Only signed app assets may supply the two scripts for local encrypted
    // Render backup. No remote shell parameters or fetched executable code.
    // Both sources are compared byte-for-byte with audited main files in CI.
    private val INSTALL_AND_START = """
import base64,gzip,hashlib,os,pathlib,sys
names=('bob_offline_key_escrow.py','bob_render_to_offline_escrow.py')
dest=pathlib.Path.home()/'bob-sicher'
dest.mkdir(mode=0o700,parents=True,exist_ok=True)
for i,name in enumerate(names):
    payload=gzip.decompress(base64.b64decode(sys.argv[1+2*i],validate=True))
    expected=sys.argv[2+2*i]
    if len(payload)>131072 or hashlib.sha256(payload).hexdigest()!=expected:
        raise ValueError('Signed application source integrity failed')
    path=dest/name
    if path.exists():
        if hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
            raise ValueError('Existing local source differs; no overwrite')
    else:
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'wb') as stream:
            stream.write(payload)
os.execv(sys.executable,(sys.executable,str(dest/names[1])))
""".trimIndent()

    fun arguments(action: Action): Array<String> = when (action) {
        Action.CHECK -> arrayOf(SCRIPT, "--help")
        // LOCAL_ESCROW requires context-specific, immutable signed source assets
        // added only inside localArguments() after the explicit on-device dialog.
        Action.LOCAL_ESCROW -> arrayOf("-c", INSTALL_AND_START)
    }

    private fun localArguments(context: Context): Array<String> {
        val result = arguments(Action.LOCAL_ESCROW).toMutableList()
        for (name in listOf("bob_offline_key_escrow.py",
                            "bob_render_to_offline_escrow.py")) {
            val bytes = context.assets.open(name).use { it.readBytes() }
            require(bytes.size in 1..131072) { "Unexpected signed asset size" }
            val hash = MessageDigest.getInstance("SHA-256").digest(bytes)
                .joinToString("") { "%02x".format(it.toInt() and 0xff) }
            val zipped = ByteArrayOutputStream()
            GZIPOutputStream(zipped).use { it.write(bytes) }
            result.add(Base64.getEncoder().encodeToString(zipped.toByteArray()))
            result.add(hash)
        }
        return result.toTypedArray()
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
        // This local-only source is bundled in the signed APK; never fetched
        // or executed from an untrusted network endpoint.
        val argv = try {
            if (isCheck) arguments(Action.CHECK) else localArguments(context)
        } catch (_: Exception) {
            return "TERMUX_LOCAL_SCRIPT_UNAVAILABLE"
        }
        val request = Intent("com.termux.RUN_COMMAND").apply {
            setClassName(PACKAGE, SERVICE)
            putExtra("com.termux.RUN_COMMAND_PATH", PYTHON)
            putExtra("com.termux.RUN_COMMAND_ARGUMENTS", argv)
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
