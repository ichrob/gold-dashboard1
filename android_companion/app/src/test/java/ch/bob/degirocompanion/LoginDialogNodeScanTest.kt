package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

class LoginDialogNodeScanTest {
    private class Node(val text: String? = null, val description: String? = null,
        val accessible: Boolean = true, val children: List<Node> = emptyList())
    private class Access : LoginDialogNodeScan.Access<Node> {
        val released = mutableListOf<Node>()
        override fun safe(node: Node) = node.accessible
        override fun labels(node: Node): List<CharSequence?> {
            check(node.accessible) { "Unsafe content must not be inspected" }
            return listOf(node.text, node.description)
        }
        override fun childCount(node: Node): Int {
            check(node.accessible) { "Unsafe descendants must not be inspected" }
            return node.children.size
        }
        override fun child(node: Node, index: Int) = node.children[index]
        override fun release(node: Node) { released += node }
    }
    private val markers = setOf(LoginDialogPolicy.NOTICE, "Schließen")
    @Test fun findsContentDescriptionOnlyNoticeWithoutProviderTextSearch() {
        val notice = Node(description = LoginDialogPolicy.NOTICE)
        val close = Node(description = "Schließen")
        val root = Node(children = listOf(Node(children = listOf(notice, close))))
        val retained = mutableListOf<Node>()
        val access = Access()
        assertTrue(LoginDialogNodeScan.collect(root, access, { it in markers }) { retained += it })
        val labels = retained.flatMap { listOfNotNull(it.text, it.description) }.toSet()
        assertEquals(LoginDialogPolicy.Kind.NOTICE, LoginDialogPolicy.identify(true, false, true, labels, false))
        assertEquals(LoginOwnerContext.DegiroScan.NOTICE_MATCH, LoginOwnerContext.scanStage(labels))
        assertEquals(listOf(notice, close), retained)
        assertEquals(3, access.released.size); assertFalse(access.released.contains(root))
    }
    @Test fun protectedEditablePasswordOrForeignSubtreeCannotSupplyMarkers() {
        val hidden = Node(description = LoginDialogPolicy.NOTICE)
        val unsafe = Node(description = LoginDialogPolicy.NOTICE, accessible = false, children = listOf(hidden))
        val close = Node(text = "Schließen")
        val access = Access()
        val retained = mutableListOf<Node>()
        assertTrue(LoginDialogNodeScan.collect(Node(children = listOf(unsafe, close)), access, { it in markers }) { retained += it })
        assertEquals(listOf(close), retained); assertFalse(access.released.contains(hidden))
        assertNull(LoginDialogPolicy.identify(true, false, true, setOf("Schließen"), false))
        assertEquals(LoginOwnerContext.DegiroScan.CLOSE_ONLY, LoginOwnerContext.scanStage(setOf("Schließen")))
    }
    @Test fun duplicateButtonsRemainDistinctForExistingUniqueTargetGuard() {
        val first = Node(text = "Schließen"); val second = Node(description = "Schließen")
        val retained = mutableListOf<Node>()
        assertTrue(LoginDialogNodeScan.collect(Node(children = listOf(first, second)), Access(), { it in markers }) { retained += it })
        assertEquals(2, retained.size); assertNotSame(retained[0], retained[1])
    }
    @Test fun nodeDepthAndMatchLimitsFailClosedAndReleaseChildren() {
        val wide = Node(children = List(300) { Node() })
        val access = Access()
        assertFalse(LoginDialogNodeScan.collect(wide, access, { false }) {})
        assertEquals(300, access.released.size)
        var deep = Node()
        repeat(26) { deep = Node(children = listOf(deep)) }
        val depthAccess = Access()
        assertFalse(LoginDialogNodeScan.collect(deep, depthAccess, { false }) {})
        assertEquals(26, depthAccess.released.size)
        assertFalse(LoginDialogNodeScan.collect(Node(children = List(81) { Node(text = "Schließen") }), Access(), { it in markers }) {})
    }
    @Test fun unrelatedLabelsAreNotRetainedAndPartialNoticeIsNotAuthorized() {
        val retained = mutableListOf<Node>()
        assertTrue(LoginDialogNodeScan.collect(Node(children = listOf(Node(text = "private unrelated label"))), Access(), { it in markers }) { retained += it })
        assertTrue(retained.isEmpty())
        assertEquals(LoginOwnerContext.DegiroScan.NO_MARKERS, LoginOwnerContext.scanStage(emptySet()))
        assertEquals(LoginOwnerContext.DegiroScan.NOTICE_TEXT_ONLY, LoginOwnerContext.scanStage(setOf(LoginDialogPolicy.NOTICE)))
        assertNull(LoginDialogPolicy.identify(true, false, true, setOf(LoginDialogPolicy.NOTICE), false))
    }
}
