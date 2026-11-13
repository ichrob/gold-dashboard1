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

    // Inspect a static node locally for fixed security terms, then discard
    // its text. Long explanatory paragraphs are neither collected nor
    // treated as credentials simply because they exceed 250 characters.
    private val protectedLabels=Regex(
        "passwort(?!\\s*(?:ändern|aendern))|password(?!\\s*change)|" +
        "pin eingeben|login|einloggen|bestätigungscode|verification code|" +
        "order bestätigen|order platzieren|place order|confirm order|limitpreis|anzahl kaufen"
    )
    fun hasProtectedLabel(label:String):Boolean =
        protectedLabels.containsMatchIn(normalize(label))

    /** Allowlist for what may enter the short-lived local enum classifier.
     * No balance, name, account number, ordinary paragraph or editable value.
     */
    fun isRelevantLabel(raw:String):Boolean {
        val line=normalize(raw)
        if(line.isBlank() || line.length>250)return false
        if(line in setOf("eur","gbp","usd","auto fx","autofx",
                "trader.currencysettings.manualactiondisabled",
                "basic","active","trader","on","off","enabled","disabled",
                "aktiv","aktiviert","eingeschaltet","ein",
                "deaktiviert","ausgeschaltet","aus",
                "währungseinstellungen","currency settings",
                "währungsumrechnung","currency conversion",
                "handelsprofil","trading profile","kontotyp","account type"))return true
        return Regex(
            "^(?:autofx|auto\\s*fx)\\s*[:=\\-]?\\s*(?:aktiviert|aktiv|eingeschaltet|ein|on|enabled|" +
                "deaktiviert|ausgeschaltet|aus|off|disabled)$"
        ).matches(line) || Regex(
            "^(?:handelsprofil|trading profile|kontotyp|account type)\\s*[:=\\-]\\s*(?:basic|active|trader)$"
        ).matches(line)
    }

    /** Exact currency table as rendered by DEGIRO even when its heading
     * scrolled out of the accessibility tree. No balance, account number or
     * action state is needed. An isolated "Auto FX" button is insufficient.
     */
    private fun currencyTable(text: List<String>): Boolean =
        setOf("eur", "gbp", "usd").all { it in text } &&
            text.count { it == "auto fx" || it == "autofx" } >= 3 &&
            text.count { it == "trader.currencysettings.manualactiondisabled" } >= 1

    fun recognizesSettings(labels: List<String>): Boolean {
        val text = labels.map(::normalize)
        return text.any { line -> setOf("währungseinstellungen", "currency settings",
            "währungsumrechnung", "currency conversion", "handelsprofil", "trading profile",
            "kontotyp", "account type").any { line == it || line.startsWith("$it:") } } ||
            currencyTable(text)
    }

    /** Only the explicit owner settings session can invoke a local read.
     * No background product heartbeat or unconfirmed page can trigger it. */
    fun ownerReadAllowed(ownerSettingsSession:Boolean,notYetRead:Boolean,code:String) =
        ownerSettingsSession && notYetRead && code=="SETTINGS_READY"

    fun read(app: String, labels: List<String>, sensitive: Boolean = false): Result {
        if (app != ProductScreenEvidence.PACKAGE) return Result("OTHER_APP")
        if (sensitive || labels.size > 500 || labels.sumOf { it.length } > 20000)
            return Result("PROTECTED_VIEW")
        val text = labels.map(::normalize).filter { it.isNotBlank() }
        if (text.any { it.length > 250 || hasProtectedLabel(it) }) return Result("PROTECTED_VIEW")

        val accountContext = text.any {
            it == "handelsprofil" || it == "trading profile" ||
            it == "kontotyp" || it == "account type" ||
            it.startsWith("handelsprofil:") || it.startsWith("trading profile:") ||
            it.startsWith("kontotyp:") || it.startsWith("account type:")
        }
        val tableConfirmed = currencyTable(text)
        val currencyContext = tableConfirmed || text.any {
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
            val explicit = Regex("^(?:autofx|auto\\s*fx)\\s*[:=\\-]?\\s*(aktiviert|aktiv|eingeschaltet|ein|on|enabled|deaktiviert|ausgeschaltet|aus|off|disabled)$")
                .matchEntire(line)?.groupValues?.get(1)
            val paired = if (line in setOf("autofx","auto fx"))
                text.getOrNull(index + 1)?.takeIf {
                    it in setOf("aktiviert", "aktiv", "eingeschaltet", "ein", "on", "enabled",
                        "deaktiviert", "ausgeschaltet", "aus", "off", "disabled")
                } else null
            when (explicit ?: paired) {
                "aktiviert", "aktiv", "eingeschaltet", "ein", "on", "enabled" -> fxStates += "ON"
                "deaktiviert", "ausgeschaltet", "aus", "off", "disabled" -> fxStates += "OFF"
            }
        }
        // On DEGIRO's actual EUR/GBP/USD table, an Auto FX badge on EVERY
        // currency plus its literal disabled-manual-action key is sufficient
        // to confirm the currently displayed Auto FX mode. Not a fee claim.
        // An explicit OFF elsewhere creates a conflict instead of a guess.
        if (tableConfirmed) fxStates += "ON"
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
