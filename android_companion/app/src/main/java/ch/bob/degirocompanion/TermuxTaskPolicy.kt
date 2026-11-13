package ch.bob.degirocompanion

/** Pure validation; consume request ID before any asynchronous execution. */
internal class TermuxTaskPolicy {
    private val seen=mutableSetOf<String>()
    fun accept(session:String,expected:String,request:String,expires:Long,now:Long,script:String):Boolean {
        if(session!=expected || !session.matches(Regex("[a-f0-9]{32}")) ||
            !request.matches(Regex("[a-f0-9]{32}")) || expires<=now || expires>now+30 ||
            script.toByteArray(Charsets.UTF_8).size !in 1..6000 || script.contains('\u0000') || seen.size>=60)return false
        return seen.add(request)
    }
}
