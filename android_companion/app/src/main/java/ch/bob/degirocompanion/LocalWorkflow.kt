package ch.bob.degirocompanion

import java.util.Locale

/** User-authored local plans only. Screen/OCR/file contents never enter this parser. */
internal enum class WorkflowAction { CLICK, WRITE, WAIT }
internal data class WorkflowStep(val action: WorkflowAction, val target: String, val value: String = "", val expected: String = "", val opensSearch: Boolean = false)
internal data class WorkflowNode(val label: String, val id: String, val editable: Boolean, val clickable: Boolean, val password: Boolean = false, val inputValue: String? = null)
internal data class WorkflowFrame(val app: String, val window: Int, val nodes: List<WorkflowNode>) {
    fun contains(text: String) = nodes.any { LocalWorkflow.normalize(it.label) == LocalWorkflow.normalize(text) }
}
internal object LocalWorkflow {
    fun normalize(s: String) = s.trim().lowercase(Locale.GERMAN).replace(Regex("\\s+"), " ")
    private val sensitive = Regex("(?i)(passwort|password|passcode|\\bpin\\b|\\btan\\b|fingerabdruck|biometric|anmelden|sign in|log.?in|kaufen|verkaufen|buy|sell|order|überweisen|transfer money|bezahlen|pay now|löschen|delete|uninstall|deinstallieren|berechtigung|permission|installieren)")
    fun safeText(text: String) = text.length in 1..300 && !sensitive.containsMatchIn(text) && text.none { it.isISOControl() }
    fun allowedApp(app: String): Boolean = Regex("[a-zA-Z][a-zA-Z0-9_]*(\\.[a-zA-Z0-9_]+)+").matches(app) &&
        !listOf("nl.degiro", "com.termux", "com.android.settings", "com.android.systemui", "com.android.packageinstaller", "com.google.android.packageinstaller", "com.samsung.android.biometrics", "ch.bob.degirocompanion").any { app.startsWith(it) }

    fun parse(input: String): List<WorkflowStep>? {
        if (input.length !in 1..5000) return null
        val lines = input.trim().lines().map { it.trim().replace('„', '"').replace('“', '"').replace('”', '"') }
        if (lines.size !in 1..12 || lines.any { it.isBlank() }) return null
        return lines.map { raw ->
            // Spoken forms remain exact grammars. Never interpret text read from a screen.
            val naturalClick = Regex("(?:tippe|klicke) auf ([^\"]+) und warte auf ([^\"]+)", RegexOption.IGNORE_CASE).matchEntire(raw)
            val naturalWrite = Regex("schreibe ([^\"]+) in ([^\"]+)", RegexOption.IGNORE_CASE).matchEntire(raw)
            val naturalWait = Regex("warte auf ([^\"]+)", RegexOption.IGNORE_CASE).matchEntire(raw)
            val line = when {
                naturalClick != null -> "Tippe auf \"${naturalClick.groupValues[1]}\" -> \"${naturalClick.groupValues[2]}\""
                naturalWrite != null -> "Schreibe \"${naturalWrite.groupValues[1]}\" in \"${naturalWrite.groupValues[2]}\""
                naturalWait != null -> "Warte auf \"${naturalWait.groupValues[1]}\""
                else -> raw
            }
            val click = Regex("(?:tippe|klicke)(?: auf)? \"([^\"]+)\" (?:->|→) \"([^\"]+)\"", RegexOption.IGNORE_CASE).matchEntire(line)
            val write = Regex("(?:schreibe|tippe) \"([^\"]+)\" in \"([^\"]+)\"", RegexOption.IGNORE_CASE).matchEntire(line)
            val wait = Regex("warte auf \"([^\"]+)\"", RegexOption.IGNORE_CASE).matchEntire(line)
            val openSearch = Regex("""Öffne Suchfeld über "([^"]+)"""", RegexOption.IGNORE_CASE).matchEntire(raw)
            val dynamicWrite = Regex("""Schreibe "([^"]+)" in das erkannte Suchfeld""", RegexOption.IGNORE_CASE).matchEntire(raw)
            val step = when {
                openSearch != null && WorkflowSearch.safeButton(openSearch.groupValues[1]) ->
                    WorkflowStep(WorkflowAction.CLICK, openSearch.groupValues[1], opensSearch=true)
                dynamicWrite != null -> WorkflowStep(WorkflowAction.WRITE, WorkflowSearch.FIELD, dynamicWrite.groupValues[1])
                click != null -> WorkflowStep(WorkflowAction.CLICK, click.groupValues[1], expected = click.groupValues[2])
                write != null -> WorkflowStep(WorkflowAction.WRITE, write.groupValues[2], value = write.groupValues[1])
                wait != null -> WorkflowStep(WorkflowAction.WAIT, wait.groupValues[1])
                else -> return null
            }
            if (!safeText(step.target) || (step.value.isNotEmpty() && !safeText(step.value)) ||
                (step.expected.isNotEmpty() && !safeText(step.expected))) return null
            step
        }
    }

    fun candidates(step: WorkflowStep, frame: WorkflowFrame): List<Int> {
        if (protected(frame)) return emptyList()
        if (step.action == WorkflowAction.WRITE && step.target == WorkflowSearch.FIELD) return WorkflowSearch.fields(frame)
        if (step.opensSearch && !WorkflowSearch.safeButton(step.target)) return emptyList()
        return frame.nodes.indices.filter { i ->
            val n = frame.nodes[i]
            (normalize(n.label) == normalize(step.target) || n.id == step.target) &&
                when (step.action) { WorkflowAction.WRITE -> n.editable && n.id.isNotBlank(); WorkflowAction.CLICK -> n.clickable; WorkflowAction.WAIT -> true }
        }
    }
    fun target(step: WorkflowStep, frame: WorkflowFrame): Int? = candidates(step, frame).singleOrNull()
    fun protected(frame: WorkflowFrame) = frame.nodes.any { it.password || sensitive.containsMatchIn(it.label) }
}

/** Exactly-once actions; only observation is retried. Failed/uncertain clicks are never replayed. */
internal class WorkflowRun(val app: String, val steps: List<WorkflowStep>, val started: Long) {
    var index = 0; private set
    var status = "Warte auf die gewählte App"; private set
    var finished = false; private set
    private var issuedAt: Long? = null
    private var baseline: WorkflowFrame? = null
    private var lastProgress = started
    private var seenTarget = false
    private var expectedId = ""
    private var expectedIndex = -1
    fun stop(reason: String) { finished = true; status = reason }
    fun tick(frame: WorkflowFrame?, now: Long, unlocked: Boolean, act: (WorkflowStep, Int) -> Boolean) {
        if (finished) return
        if (!unlocked) return stop("Gestoppt: Bildschirm gesperrt")
        if (now - started > 180_000 || now - lastProgress > 20_000) return stop("Zeitlimit: Ergebnis nicht bestätigt (Schritt ${index + 1})")
        if (frame == null) return
        if (frame.app != app) {
            if (seenTarget) stop("Gestoppt: andere App im Vordergrund")
            return
        }
        seenTarget = true
        if (LocalWorkflow.protected(frame)) return stop("Gestoppt: geschützte Ansicht; keine Aktion")
        val step = steps[index]
        if (issuedAt != null) {
            val verified = when (step.action) {
                WorkflowAction.CLICK -> frame != baseline && if (step.opensSearch)
                    WorkflowSearch.fields(frame).size == 1 else frame.contains(step.expected)
                WorkflowAction.WRITE -> {
                    val candidates = frame.nodes.withIndex().filter { it.value.editable &&
                        if (expectedId.isNotBlank()) it.value.id == expectedId else it.index == expectedIndex && frame.window == baseline?.window }
                    candidates.singleOrNull()?.value?.inputValue == step.value
                }
                WorkflowAction.WAIT -> frame.contains(step.target)
            }
            if (verified) advance(now)
            return
        }
        if (step.action == WorkflowAction.WAIT) {
            if (frame.contains(step.target)) advance(now)
            return
        }
        val matches = LocalWorkflow.candidates(step, frame)
        if (matches.isEmpty()) { status = "Warte auf eindeutiges Ziel: ${step.target}"; return }
        val node = matches.singleOrNull() ?: return stop("Ziel ist mehrdeutig: ${step.target}")
        // A click needs a NEW expected observation, not text already present beforehand.
        if (step.action == WorkflowAction.CLICK && (if (step.opensSearch)
            WorkflowSearch.fields(frame).isNotEmpty() else frame.contains(step.expected)))
            return stop("Ergebnis schon sichtbar: Bitte ein eindeutiges neues Klick-Ergebnis angeben")
        baseline = frame; expectedId = frame.nodes[node].id; expectedIndex = node
        issuedAt = now
        status = "Schritt ${index + 1}: Aktion angefordert; prüfe Ergebnis"
        if (!act(step, node)) stop("Aktion abgelehnt; kein automatischer Wiederholungsklick")
    }
    private fun advance(now: Long) {
        index++; issuedAt = null; baseline = null; lastProgress = now
        if (index == steps.size) stop("Erfolgreich: alle $index Schritte am Bildschirm bestätigt")
        else status = "Schritt $index bestätigt; weiter mit ${index + 1}"
    }
}
