package ch.bob.degirocompanion
import org.junit.Assert.*
import org.junit.Test
class SearchTapPolicyTest {
    private val screen=SearchTapPolicy.Box(0,0,720,1600)
    @Test fun usesCurrentNodeCenter() {
        assertEquals(350 to 340,SearchTapPolicy.center(SearchTapPolicy.Box(40,300,660,380),screen))
        assertEquals(650 to 100,SearchTapPolicy.center(SearchTapPolicy.Box(620,70,680,130),screen))
    }
    @Test fun rejectsClippedEmptyOversizedAndInvalidBounds() {
        for(box in listOf(SearchTapPolicy.Box(-1,300,660,380),SearchTapPolicy.Box(40,-1,660,80),
                SearchTapPolicy.Box(40,300,721,380),SearchTapPolicy.Box(40,1590,660,1610),
                SearchTapPolicy.Box(40,300,40,380),SearchTapPolicy.Box(40,300,660,301),
                SearchTapPolicy.Box(0,0,720,1600),SearchTapPolicy.Box(Int.MIN_VALUE,0,Int.MAX_VALUE,100)))
            assertNull(SearchTapPolicy.center(box,screen))
    }
}
