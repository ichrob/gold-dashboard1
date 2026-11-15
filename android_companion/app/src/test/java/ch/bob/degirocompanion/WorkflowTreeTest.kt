package ch.bob.degirocompanion
import org.junit.Assert.*
import org.junit.Test
class WorkflowTreeTest {
    private class Node(val name: String, val children: List<Node> = emptyList())
    private fun read(node: Node) = WorkflowTree.read(node,{ it.children.size },{ n,i -> n.children[i] })
    @Test fun handlesWideAndDeepTreesBeyondOldLimits() {
        val wide = Node("root",(0..499).map { Node("$it") })
        assertEquals(501,read(wide).nodes.size)
        assertEquals("499",read(wide).nodes.last().name)
        var deep = Node("leaf")
        repeat(60) { deep = Node("parent",listOf(deep)) }
        assertEquals(61,read(deep).nodes.size)
        assertEquals("leaf",read(deep).nodes.last().name)
    }
    @Test fun limitsNeverReturnAnActionablePartialTree() {
        val branch = Node("branch",(1..1000).map { Node("leaf") })
        val over = read(Node("root",List(5) { branch }))
        assertEquals("NODE_LIMIT",over.error); assertTrue(over.nodes.isEmpty())
        assertEquals("CHILD_LIMIT",read(Node("root",List(1025) { Node("leaf") })).error)
        var deep = Node("leaf")
        repeat(82) { deep = Node("parent",listOf(deep)) }
        assertEquals("DEPTH_LIMIT",read(deep).error)
        val changing = WorkflowTree.read(Node("root"),{ 1 },{ _,_ -> null })
        assertEquals("CHANGED",changing.error); assertTrue(changing.nodes.isEmpty())
    }
    @Test fun preservesOrderAndInspectsTailAfterOldFourHundredNodeCutoff() {
        val tree = read(Node("root",List(500) { Node("ordinary") }+Node("Passwort")))
        assertTrue(tree.complete)
        assertEquals("Passwort",tree.nodes.last().name)
        assertTrue(LocalWorkflow.protected(WorkflowFrame("org.fixture.app",1,tree.nodes.map { WorkflowNode(it.name,"",false,false) })))
    }
}
