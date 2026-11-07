package ch.bob.degirocompanion

/** Explicit app-scoped demonstration produces a draft, never an executable/cache-approved plan. */
internal class WorkflowDemonstration(val app: String) {
    val steps = mutableListOf<WorkflowStep>()
    var error = ""; private set
    private var beforeClick = emptySet<String>()
    private var pending = -1
    private fun add(step: WorkflowStep) {
        if (steps.size >= 12) { error = "Zwölf Schritte erreicht; Aufzeichnung beendet"; return }
        steps += step
    }
    fun click(target: String, frame: WorkflowFrame) {
        if (error.isNotEmpty() || frame.app != app || LocalWorkflow.protected(frame)) return
        if (!WorkflowComposer.validText(target)) { error = "Symbol ohne Beschriftung: zuerst über Screenshot erklären"; return }
        add(WorkflowStep(WorkflowAction.CLICK, target, expected = "ERGEBNISTEXT"))
        pending = steps.lastIndex; beforeClick = frame.nodes.map { it.label }.toSet()
    }
    fun write(target: String, value: String) {
        if (error.isNotEmpty()) return
        if (!WorkflowComposer.validText(target) || (value.isNotEmpty() && !WorkflowComposer.validText(value))) {
            error = "Diese Eingabe wird nicht aufgezeichnet"; return
        }
        val last = steps.lastOrNull()
        if (last?.action == WorkflowAction.WRITE && last.target == target) steps.removeAt(steps.lastIndex)
        add(WorkflowStep(WorkflowAction.WRITE, target, value.ifEmpty { "TEXT" }))
    }
    fun observe(frame: WorkflowFrame) {
        if (frame.app != app || LocalWorkflow.protected(frame)) return
        val step = steps.getOrNull(pending) ?: return
        if (step.expected != "ERGEBNISTEXT") return
        val labels = frame.nodes.filter { !it.editable || it.inputValue.isNullOrEmpty() }.map { it.label }.filter {
            it !in beforeClick && WorkflowComposer.validText(it) && it != step.target
        }.distinct()
        labels.singleOrNull()?.let { steps[pending] = step.copy(expected = it); pending = -1 }
    }
    fun draft() = steps.toList()
}
