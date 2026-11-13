package ch.bob.degirocompanion

import java.util.Locale

/**
 * Read-only, redacted classification of a user-opened DEGIRO settings screen.
 * Never contains raw screen text, account details, a quote, or a fee approval.
 * Missing/conflicting labels are unknown, never inferred from defaults.
 */
internal object AccountSettingsEvidence {
    data class Result(val code: String, val feeProfile: String? = null, val autoFx: String? = null)

    private fun normalize(s: String) = s.trim().lowercase(Locale.ROOT)
        .replace(Regex("\\s+"), " ")

    fun read(app: String, labels: List<String>, sensitive: Boolean = false): Result {
        if (app != ProductScreenEvidence.PACKAGE) return Result("OTHER_APP")
        if (sensitive || labels.size > 500 || labels.sumOf { it.length } > 20000)
            return Result("PROTECTED_VIEW")
        val text = labels.map(::normalize).filter { it.isNotBlank() }
        if (text.any { it.length > 250 || Regex(
                "passwort(?!\\\\s*(?:ändern|aendern))|password(?!\\\\s*change)|pin eingeben|login|einloggen|bestätigungscode|verification code|" +
                "order bestätigen|order platzieren|place order|confirm order|limitpreis|anzahl kaufen"
            ).containsMatchIn(it) }) return Result("PROTECTED_VIEW")

        val accountContext = text.any {
            it == "handelsprofil" || it == "trading profile" ||
            it == "kontotyp" || it == "account type" ||
            it.startsWith("handelsprofil:") || it.startsWith("trading profile:") ||
            it.startsWith("kontotyp:") || it.startsWith("account type:")
        }
        val currencyContext = text.any {
            it == "währungseinstellungen" || it == "currency settings" ||
            it == "währungsumrechnung" || it == "currency conversion" ||
            it.startsWith("währungseinstellungen:") || it.startsWith("currency settings:")
        }
        if (!accountContext && !currencyContext) return Result("SETTINGS_NOT_VISIBLE")

        val profiles = mutableSetOf<String>()
        if (accountContext) text.forEachIndexed { index, line ->
            val embedded = Regex("^(?:handelsprofil|trading profile|kontotyp|account type)\\s*[:=\\-]\\s*(basic|active|trader)$")
                .matchEntire(line)?.groupValues?.get(1)
            val paired = if (line in setOf("handelsprofil", "trading profile", "kontotyp", "account type"))
                text.getOrNull(index + 1)?.takeIf { it in setOf("basic", "active", "trader") } else null
            (embedded ?: paired)?.let { profiles += it.uppercase(Locale.ROOT) }
        }

        val fxStates = mutableSetOf<String>()
        if (currencyContext) text.forEachIndexed { index, line ->
            val explicit = Regex("^autofx\\s*[:=\\-]?\\s*(aktiviert|aktiv|eingeschaltet|ein|on|enabled|deaktiviert|ausgeschaltet|aus|off|disabled)$")
                .matchEntire(line)?.groupValues?.get(1)
            val paired = if (line == "autofx")
                text.getOrNull(index + 1)?.takeIf {
                    it in setOf("aktiviert", "aktiv", "eingeschaltet", "ein", "on", "enabled",
                        "deaktiviert", "ausgeschaltet", "aus", "off", "disabled")
                } else null
            when (explicit ?: paired) {
                "aktiviert", "aktiv", "eingeschaltet", "ein", "on", "enabled" -> fxStates += "ON"
                "deaktiviert", "ausgeschaltet", "aus", "off", "disabled" -> fxStates += "OFF"
            }
        }
        // Conflicting settings are an unsafe observation, not a best-effort guess.
        if (profiles.size > 1 || fxStates.size > 1) return Result("SETTINGS_CONFLICT")
        val profile = profiles.singleOrNull()
        val fx = fxStates.singleOrNull()
        return when {
            profile != null && fx != null -> Result("ACCOUNT_SETTINGS_COMPLETE", profile, fx)
            profile != null || fx != null -> Result("ACCOUNT_SETTINGS_PARTIAL", profile, fx)
            else -> Result("SETTINGS_UNCONFIRMED")
        }
    }
}
