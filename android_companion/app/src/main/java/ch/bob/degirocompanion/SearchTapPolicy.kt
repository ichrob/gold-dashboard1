package ch.bob.degirocompanion

/** Coordinates come only from a freshly policy-validated search node. */
internal object SearchTapPolicy {
    data class Box(val left:Int,val top:Int,val right:Int,val bottom:Int)
    fun center(target:Box,screen:Box): Pair<Int,Int>? {
        val width=target.right.toLong()-target.left
        val height=target.bottom.toLong()-target.top
        val sw=screen.right.toLong()-screen.left
        val sh=screen.bottom.toLong()-screen.top
        if(screen.left<0 || screen.top<0 || sw<=0 || sh<=0) return null
        if(width<8 || height<8 || height>sh/4 || width>sw ||
            target.left<screen.left || target.top<screen.top || target.right>screen.right || target.bottom>screen.bottom) return null
        return (target.left+width/2).toInt() to (target.top+height/2).toInt()
    }
}
