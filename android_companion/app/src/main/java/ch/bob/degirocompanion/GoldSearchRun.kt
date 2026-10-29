package ch.bob.degirocompanion

/** One explicitly started search, bounded by ProductReadRequest's deadline. */
internal object GoldSearchRun {
    var running=false; private set
    var lastCode:String?=null; private set
    var lastEventAt:String?=null; private set
    fun start() { running=true;lastCode=null;lastEventAt=null }
    fun event(code:String, at:String) { lastCode=PhoneDiagnosticPolicy.code(code);lastEventAt=at }
    fun stop(code:String, at:String) {
        if(running) event(code,at)
        running=false
    }
    fun clear() { running=false;lastCode=null;lastEventAt=null }
}
