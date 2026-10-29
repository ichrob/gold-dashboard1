package ch.bob.degirocompanion

/** Bound to the locally opened session; duplicates are consumed before executing. */
internal class PhoneCommandPolicy {
    private val seen=mutableSetOf<String>()
    fun accept(session:String,expected:String,request:String,action:String,isin:String,expires:Long,now:Long):Boolean {
        if(session!=expected || !session.matches(Regex("[a-f0-9]{32}")) || !request.matches(Regex("[a-f0-9]{32}")) || expires<=now || expires>now+30)return false
        if(action !in setOf("inspect","search_gold","search_isin","read_page","stop"))return false
        if(action=="search_isin") { if(!SeriesEvidence.validIsin(isin))return false } else if(isin.isNotEmpty())return false
        if(seen.size>120 || (seen.size>=120 && action!="stop"))return false
        return seen.add(request)
    }
}
