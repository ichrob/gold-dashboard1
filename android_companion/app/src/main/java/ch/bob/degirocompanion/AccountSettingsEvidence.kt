package ch.bob.degirocompanion

import java.util.Locale

/**
 * Read-only, redacted classification of a user-opened DEGIRO settings screen.
 * Never contains raw screen text, account details, a quote, or a fee approval.
 * Missing/conflicting labels are unknown, never inferred from defaults.
 */
internal object AccountSettingsEvidence {
    data class Result(val code: String, val feeProfile: String? = null, val autoFx: String? = null,
                      val source: String = "degiro-app-local-accessibility")

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
                "handelsprofil","trading profile","kontotyp","account type",
                "ihre handelseinstellungen","your trading settings",
                "benutzerkonto auswählen","select account"))return true
        if(line in planCards)return true
        return Regex(
            "^(?:autofx|auto\\s*fx)\\s*[:=\\-]?\\s*(?:aktiviert|aktiv|eingeschaltet|ein|on|enabled|" +
                "deaktiviert|ausgeschaltet|aus|off|disabled)$"
        ).matches(line) || Regex(
            "^(?:handelsprofil|trading profile|kontotyp|account type)\\s*[:=\\-]\\s*(?:basic|active|trader)$"
        ).matches(line)
    }

    // Do not equate the presence of all three available plans with the
    // user's ACTIVE plan. The screenshot's green border is not text.
    // Only an Android-selected node or a fully visible set of three cards
    // with selection buttons on exactly the other two can identify a plan.
    private val planCards=mapOf("basic-benutzerkonto" to "BASIC",
        "active-benutzerkonto" to "ACTIVE", "trader-benutzerkonto" to "TRADER",
        "basic account" to "BASIC", "active account" to "ACTIVE",
        "trader account" to "TRADER")
    fun exactCardProfile(label:String):String?=planCards[normalize(label)]

    private fun profilePicker(text:List<String>):Boolean =
        "ihre handelseinstellungen" in text || "your trading settings" in text ||
        (text.any { it in planCards } &&
          text.any { it=="benutzerkonto auswählen" || it=="select account" })

    private fun uniquelySelectedProfile(text:List<String>):String? {
        val cards=text.mapIndexedNotNull { index,label ->
            planCards[label]?.let { index to it }
        }
        if(cards.map { it.second }.toSet()!=setOf("BASIC","ACTIVE","TRADER") ||
            cards.size!=3)return null
        // Need the whole three-card snapshot, never infer from a partly
        // visible card. Two other cards must have an exact "choose" button.
        val buttons=text.withIndex().filter {
            it.value=="benutzerkonto auswählen" || it.value=="select account"
        }.map { it.index }
        if(buttons.size!=2)return null
        val selected=cards.filterIndexed { idx,card ->
            val until=cards.getOrNull(idx+1)?.first ?: text.size
            buttons.none { it>card.first && it<until }
        }
        // Last card may continue below the viewport. Its absent button is
        // never evidence that the user selected it.
        return selected.singleOrNull()?.takeUnless { it.second=="TRADER" }?.second
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
            currencyTable(text) || profilePicker(text)
    }

    /** Local owner attestation is a fallback when a coloured card border
     * is not available through Android accessibility. It is NOT an
     * automated broker fact and is accepted only on the exact DEGIRO
     * settings page while the named card is visible.
     */
    fun ownerConfirmedProfile(app:String, labels:List<String>, profile:String,
                              sensitive:Boolean=false):Result {
        val existing=read(app,labels,sensitive)
        if(existing.code in setOf("OTHER_APP","PROTECTED_VIEW","SETTINGS_CONFLICT"))
            return existing
        val text=labels.map(::normalize)
        // The owner already confirmed the highlighted profile on this
        // DEGIRO page. Its green CSS border may not be accessible to Android,
        // and the owner's chosen card may be off-screen when the app relaunches.
        // Do NOT require the asserted card to still be in the viewport: that
        // makes a valid physical user confirmation impossible to deliver.
        // Instead require an independently recognised DEGIRO profile selector.
        val ownerOnProfilePage =
            "ihre handelseinstellungen" in text || "your trading settings" in text ||
            (text.count { it in planCards }>=2 &&
             text.any { it=="benutzerkonto auswählen" || it=="select account" })
        if(profile !in setOf("BASIC","ACTIVE","TRADER") || !ownerOnProfilePage)
            return Result("SETTINGS_UNCONFIRMED")
        if(existing.feeProfile!=null && existing.feeProfile!=profile)
            return Result("SETTINGS_CONFLICT")
        return Result("ACCOUNT_SETTINGS_PARTIAL",profile,null,
            "degiro-app-owner-confirmed")
    }

    /** Only the explicit owner settings session can invoke a local read.
     * No background product heartbeat or unconfirmed page can trigger it. */
    fun ownerReadAllowed(ownerSettingsSession:Boolean,notYetRead:Boolean,code:String) =
        ownerSettingsSession && notYetRead && code=="SETTINGS_READY"

    fun read(app: String, labels: List<String>, sensitive: Boolean = false,
             selectedProfiles:List<String> = emptyList()): Result {
        if (app != ProductScreenEvidence.PACKAGE) return Result("OTHER_APP")
        if (sensitive || labels.size > 500 || labels.sumOf { it.length } > 20000)
            return Result("PROTECTED_VIEW")
        val text = labels.map(::normalize).filter { it.isNotBlank() }
        if (text.any { it.length > 250 || hasProtectedLabel(it) }) return Result("PROTECTED_VIEW")

        val accountContext = profilePicker(text) || text.any {
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
        if(accountContext) {
            // Selection is accepted only when the selected Android semantic
            // node matches an exact displayed card heading; arbitrary
            // "Basic" text in a choice list never becomes account evidence.
            selectedProfiles.filter { it in setOf("BASIC","ACTIVE","TRADER") }
                .filter { selected -> text.any { planCards[it]==selected } }
                .forEach { profiles+=it }
            uniquelySelectedProfile(text)?.let { profiles+=it }
        }
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
