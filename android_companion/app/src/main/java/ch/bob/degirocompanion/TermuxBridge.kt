package ch.bob.degirocompanion

import android.content.Context
import android.content.Intent

/**
 * Explicit, fixed local bridge to the official Termux RUN_COMMAND service.
 * No generic shell, untrusted arguments, device file reads, or remote secret output.
 * "TERMUX_REQUESTED" only means Android accepted an Intent, NOT that Python
 * ran or that an encrypted archive was saved.
 */
internal object TermuxBridge {
    enum class Action { CHECK, LOCAL_ESCROW }

    const val PACKAGE = "com.termux"
    const val SERVICE = "com.termux.app.RunCommandService"
    const val PYTHON = "/data/data/com.termux/files/usr/bin/python"
    const val SCRIPT = "/data/data/com.termux/files/home/bob-sicher/bob_offline_key_escrow.py"
    const val OUTPUT = "/data/data/com.termux/files/home/bob-sicher/bob-archive-root.vault"

    fun arguments(action: Action): Array<String> = when (action) {
        Action.CHECK -> arrayOf(SCRIPT, "--help")
        Action.LOCAL_ESCROW -> arrayOf(SCRIPT, "create", "--output", OUTPUT)
    }

    fun launch(context: Context, action: Action): String {
        // The user must install Termux and explicitly grant RUN_COMMAND.
        // A fixed local Python program is the only permitted entrypoint.
        if (context.packageManager.getLaunchIntentForPackage(PACKAGE) == null)
            return "TERMUX_NOT_INSTALLED"
        val request = Intent("com.termux.RUN_COMMAND").apply {
            setClassName(PACKAGE, SERVICE)
            putExtra("com.termux.RUN_COMMAND_PATH", PYTHON)
            putExtra("com.termux.RUN_COMMAND_ARGUMENTS", arguments(action))
            putExtra("com.termux.RUN_COMMAND_WORKDIR",
                "/data/data/com.termux/files/home")
            putExtra("com.termux.RUN_COMMAND_BACKGROUND", false)
            putExtra("com.termux.RUN_COMMAND_SESSION_ACTION", "0")
        }
        return try {
            if (context.startService(request) == null)
                "TERMUX_UNAVAILABLE" else "TERMUX_REQUESTED"
        } catch (_: SecurityException) {
            "TERMUX_PERMISSION_REQUIRED"
        } catch (_: IllegalStateException) {
            "TERMUX_START_RESTRICTED"
        } catch (_: RuntimeException) {
            "TERMUX_UNAVAILABLE"
        }
    }
}
