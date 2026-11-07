package ch.bob.degirocompanion

/** One explicitly started search, bounded by ProductReadRequest's deadline. */
internal object GoldSearchRun {
    var running=false; private set
    var lastCode:String?=null; private set
    var lastEventAt:String?=null; private set
    var searchOnlyQuery: String? = null; private set
    val query get() = searchOnlyQuery ?: "Gold"
    fun start() { searchOnlyQuery=null;running=true;lastCode=null;lastEventAt=null }
    fun startSearch(query: String) {
        require(query in setOf("Gold","Silber"))
        start(); searchOnlyQuery=query
    }
    fun event(code:String, at:String) { lastCode=PhoneDiagnosticPolicy.code(code);lastEventAt=at }
    fun stop(code:String, at:String) {
        if(running) event(code,at)
        running=false
    }
    fun clear() { searchOnlyQuery=null;running=false;lastCode=null;lastEventAt=null }
}
