package ch.bob.degirocompanion

/** Explicit app-scoped demonstration produces a draft, never an executable/cache-approved plan. */
internal class WorkflowDemonstration(val app: String) {
    val steps = mutableListOf<WorkflowStep>()
    val choices = mutableMapOf<Int, List<String>>()
    var error = ""; private set
    private var beforeClick = emptySet<String>()
    private var pending = -1
    private var previousFrame: WorkflowFrame? = null
    private var inferredTarget: String? = null
    private fun add(step: WorkflowStep) {
        if (steps.size >= 12) { error = "Zwölf Schritte erreicht; Aufzeichnung beendet"; return }
        steps += step
    }
    fun click(target: String, frame: WorkflowFrame) {
        if (error.isNotEmpty() || frame.app != app || LocalWorkflow.protected(frame)) return
        if (!WorkflowComposer.validText(target)) { error = "Symbol ohne Beschriftung: zuerst über Screenshot erklären"; return }
        if (inferredTarget == target && steps.any { it.action == WorkflowAction.CLICK && it.target == target && it.expected == "ERGEBNISTEXT" }) { inferredTarget = null; return }
        inferredTarget = null; previousFrame = frame
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
        val previous = previousFrame
        previousFrame = frame
        if (previous != null && previous != frame && pending < 0) {
            fun identity(node: WorkflowNode) = node.id.ifBlank { node.label }
            val remaining = frame.nodes.map { identity(it) }.toSet()
            val gone = previous.nodes.filter { it.clickable && !it.editable && !it.password && identity(it) !in remaining && WorkflowComposer.validText(identity(it)) }
                .distinctBy { identity(it) }.singleOrNull()
            if (gone != null && steps.lastOrNull()?.let { it.action == WorkflowAction.CLICK && it.target == identity(gone) } != true) {
                if (steps.size >= 12) { error = "Zwölf Schritte erreicht; Aufzeichnung beendet"; return }
                val target = identity(gone)
                // A disappearing view may omit its click event. This is only a tentative
                // draft step: retain ERGEBNISTEXT until the owner explicitly reviews it.
                val index = steps.indexOfLast { it.action == WorkflowAction.WRITE && it.target in remaining && previous.nodes.none { node -> identity(node) == it.target } }
                val insertAt = if (index >= 0) index else steps.size
                choices.keys.sortedDescending().filter { it >= insertAt }.forEach { choices[it + 1] = choices.remove(it)!! }
                choices[insertAt] = frame.nodes.map { it.label }.filter { label ->
                    label !in previous.nodes.map { it.label } && WorkflowComposer.validText(label)
                }.distinct().take(30)
                steps.add(insertAt, WorkflowStep(WorkflowAction.CLICK,target,expected="ERGEBNISTEXT"))
                inferredTarget = target
            }
        }
        val step = steps.getOrNull(pending) ?: return
        if (step.expected != "ERGEBNISTEXT") return
        if (WorkflowSearch.safeButton(step.target) && WorkflowSearch.fields(frame).size == 1) {
            steps[pending] = step.copy(expected="", opensSearch=true); pending = -1; return
        }
        if (WorkflowNavigation.isTab(step.target) && WorkflowNavigation.selected(step, frame)) {
            steps[pending] = step.copy(expected="", selectsTab=true); pending = -1; return
        }
        val labels = frame.nodes.filter { !it.editable || it.inputValue.isNullOrEmpty() }.map { it.label }.filter {
            it !in beforeClick && WorkflowComposer.validText(it) && it != step.target
        }.distinct()
        choices[pending] = labels.take(30)
        labels.singleOrNull()?.let { steps[pending] = step.copy(expected = it); pending = -1 }
    }
    fun draft() = steps.toList()
}
