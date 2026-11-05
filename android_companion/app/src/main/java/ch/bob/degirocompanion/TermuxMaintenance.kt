package ch.bob.degirocompanion

import android.app.Activity
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import org.json.JSONObject
import java.util.UUID
import java.util.concurrent.Executors

/** Separate, explicit local consent. This is Termux-UID execution, NOT a sandbox. */
internal object TermuxMaintenance {
    const val RESULT_ACTION="ch.bob.degirocompanion.TERMUX_MAINTENANCE_RESULT"
    private val handler=Handler(Looper.getMainLooper())
    private val network=Executors.newSingleThreadExecutor()
    private var session=""
    private var expires=0L
    private var deadline=0L
    private var pending=""
    private var pendingIntent:PendingIntent?=null
    private var result:JSONObject?=null
    private var policy=TermuxTaskPolicy()
    var message="Termux-Wartung ausgeschaltet."
        private set
    fun active()=session.isNotEmpty() && SystemClock.elapsedRealtime()<deadline
    fun start(c:Context) {
        check(PhoneDiagnostics.paired(c)) { "Zuerst Bob-Diagnose verbinden." }
        check(!active() && pending.isEmpty()) { "Vorherige Wartung zuerst beenden." }
        check(c.packageManager.getLaunchIntentForPackage(TermuxBridge.PACKAGE)!=null) { "Termux fehlt." }
        session=UUID.randomUUID().toString().replace("-","");policy=TermuxTaskPolicy();result=null
        deadline=SystemClock.elapsedRealtime()+1800000;expires=System.currentTimeMillis()/1000+1800
        message="Termux-Wartung aktiv · 30 Minuten · Shellzugriff mit Termux-Rechten."
        val id=session
        handler.postDelayed({if(session==id)stop(c)},1800000)
        poll(c.applicationContext,id)
    }
    private fun payload(id:String,enabled:Boolean)=JSONObject().put("sessionId",id)
        .put("expiresAt",expires).put("active",enabled).put("result",result ?: JSONObject.NULL)
    fun stop(c:Context) {
        if(session.isEmpty())return
        val id=session;val body=payload(id,false)
        session="";deadline=0;pending="";pendingIntent?.cancel();pendingIntent=null;result=null
        message="Termux-Wartung beendet. Laufender Befehl hat höchstens 20 Sekunden Laufzeit; keine neuen Aufträge."
        network.execute { runCatching {PhoneDiagnostics.termuxExchange(c.applicationContext,body)} }
    }
    private fun poll(c:Context,id:String) {
        if(session!=id)return
        if(!active() || !PhoneDiagnostics.paired(c)) {stop(c);return}
        val body=payload(id,true)
        network.execute {
            val response=runCatching {PhoneDiagnostics.termuxExchange(c,body)}
            handler.post {
                if(session!=id)return@post
                if(!active()) {stop(c);return@post}
                response.onSuccess { reply ->
                    if(reply.optString("sessionId")!=id) {stop(c);return@onSuccess}
                    reply.optJSONObject("command")?.let { task ->
                        val request=task.optString("requestId");val now=System.currentTimeMillis()/1000
                        val script=task.optString("script")
                        if(pending.isEmpty() && policy.accept(task.optString("sessionId"),id,
                            request,task.optLong("expiresAt"),now,script)) {
                            launch(c,id,request,script)
                        }
                    }
                }.onFailure { message="Termux-Wartung: Verbindung unterbrochen; Ausführung nicht bestätigt." }
                if(session==id)handler.postDelayed({poll(c,id)},2500)
            }
        }
    }
    private fun launch(c:Context,id:String,request:String,script:String) {
        pending=request;result=null
        try {
            val source=c.assets.open("bob_termux_runner.py").use { it.readBytes() }
            check(source.size in 1..16384)
            val callback=Intent(c,TermuxMaintenanceResultReceiver::class.java).setAction(RESULT_ACTION)
                .putExtra("bobSession",id).putExtra("bobRequest",request)
            val flags=PendingIntent.FLAG_ONE_SHOT or (if(Build.VERSION.SDK_INT>=31) PendingIntent.FLAG_MUTABLE else 0)
            pendingIntent=PendingIntent.getBroadcast(c,request.hashCode(),callback,flags)
            val intent=Intent("com.termux.RUN_COMMAND").setClassName(TermuxBridge.PACKAGE,TermuxBridge.SERVICE)
                .putExtra("com.termux.RUN_COMMAND_PATH",TermuxBridge.PYTHON)
                .putExtra("com.termux.RUN_COMMAND_ARGUMENTS",arrayOf("-c",String(source,Charsets.UTF_8),script))
                .putExtra("com.termux.RUN_COMMAND_WORKDIR","/data/data/com.termux/files/home")
                .putExtra("com.termux.RUN_COMMAND_BACKGROUND",true)
                .putExtra("com.termux.RUN_COMMAND_PENDING_INTENT",pendingIntent)
            check(c.startService(intent)!=null)
            message="Termux-Auftrag übergeben; Ergebnis steht aus."
            handler.postDelayed({if(session==id && pending==request)finish(id,request,"unconfirmed","",-999)},30000)
        } catch (_:Exception) {finish(id,request,"launch-failed","",-999)}
    }
    fun receive(intent:Intent) {
        val id=intent.getStringExtra("bobSession").orEmpty()
        val request=intent.getStringExtra("bobRequest").orEmpty()
        if(!active() || session!=id || pending!=request)return
        val bundle=intent.getBundleExtra("result")
        try {
            check(bundle!=null && bundle.containsKey("err") && bundle.getInt("err")==Activity.RESULT_OK)
            check(bundle.containsKey("exitCode") && bundle.getInt("exitCode")==0)
            val stdout=bundle.getString("stdout").orEmpty();check(stdout.toByteArray().size<=65536)
            val parsed=JSONObject(stdout)
            val status=parsed.getString("status");val output=parsed.getString("output");val exit=parsed.getInt("exitCode")
            check(status in setOf("completed","timeout","output-limit","launch-failed"))
            check(output.toByteArray(Charsets.UTF_8).size<=8192 && exit in -999..255)
            finish(id,request,status,output,exit)
        } catch (_:Exception) {finish(id,request,"unconfirmed","",-999)}
    }
    private fun finish(id:String,request:String,status:String,output:String,exit:Int) {
        if(session!=id || pending!=request)return
        result=JSONObject().put("requestId",request).put("status",status).put("output",output).put("exitCode",exit)
        pending="";pendingIntent?.cancel();pendingIntent=null
        message="Letzter Termux-Auftrag: $status · Exitcode $exit."
    }
}
