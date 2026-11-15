package ch.bob.degirocompanion

import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.json.JSONObject
import java.net.ServerSocket
import java.util.concurrent.atomic.AtomicReference

/** Runs the actual native chat against a loopback fixture, never Google/Termux. */
@RunWith(AndroidJUnit4::class)
class GeminiChatDeviceTest {
    private fun descendants(v: View): List<View> = listOf(v) +
        if (v is ViewGroup) (0 until v.childCount).flatMap { descendants(v.getChildAt(it)) } else emptyList()

    @Test fun nativeChatSendsTextAndShowsOneShotPermissionWithoutCloud() {
        GeminiLocalSession.stop()
        val server = ServerSocket(0, 4, java.net.InetAddress.getByName("127.0.0.1"))
        val received = AtomicReference<JSONObject>()
        val permission = AtomicReference<JSONObject>()
        val fixtureToken = "b".repeat(64)
        val running = java.util.concurrent.atomic.AtomicBoolean(true)
        val worker = Thread {
            while (running.get()) {
                try {
                    server.accept().use { socket ->
                        socket.soTimeout = 5000
                        val reader = socket.getInputStream().bufferedReader()
                        val first = reader.readLine() ?: return@use
                        val headers = mutableMapOf<String, String>()
                        while (true) {
                            val line = reader.readLine() ?: break
                            if (line.isEmpty()) break
                            val split = line.indexOf(':')
                            if (split > 0) headers[line.substring(0, split).lowercase()] = line.substring(split + 1).trim()
                        }
                        assertEquals("Bearer $fixtureToken", headers["authorization"])
                        val n = headers["content-length"]?.toInt() ?: 0
                        val body = CharArray(n)
                        var offset = 0
                        while (offset < n) { val read = reader.read(body, offset, n-offset); if (read < 0) break; offset += read }
                        if (first.startsWith("POST /prompt ")) received.set(JSONObject(String(body)))
                        if (first.startsWith("POST /permission ")) permission.set(JSONObject(String(body)))
                        val pending = if (received.get() != null && permission.get() == null)
                            """[{"id":"fixture-permission","details":"Run public regression test","options":[{"id":"once","kind":"allow_once"},{"id":"no","kind":"reject_once"}]}]""" else "[]"
                        val answer = JSONObject.quote(("Verarbeitungsschritt abgeschlossen.\n").repeat(180))
                        val response = if (first.startsWith("GET /status "))
                            """{"state":"ready","events":[{"id":1,"kind":"answer","text":$answer}],"permissions":$pending}"""
                            else """{"accepted":true}"""
                        val bytes = response.toByteArray()
                        socket.getOutputStream().write(("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: ${bytes.size}\r\nConnection: close\r\n\r\n").toByteArray())
                        socket.getOutputStream().write(bytes)
                    }
                } catch (_: Exception) { if (running.get()) throw AssertionError("Local fixture failed") }
            }
        }.apply { isDaemon = true; start() }
        fun setField(name: String, value: Any) {
            GeminiLocalSession::class.java.getDeclaredField(name).apply { isAccessible = true }.set(null, value)
        }
        setField("port", server.localPort); setField("token", fixtureToken)
        setField("startedAt", System.currentTimeMillis())
        try {
            ActivityScenario.launch(GeminiChatActivity::class.java).use { scenario ->
                fun waitFor(test: (List<View>) -> Boolean) {
                    val end = System.currentTimeMillis() + 10000
                    while (System.currentTimeMillis() < end) {
                        var ok = false
                        scenario.onActivity { a -> ok = test(descendants(a.window.decorView)) }
                        if (ok) return
                        Thread.sleep(100)
                    }
                    fail("Native chat condition not reached")
                }
                waitFor { views -> views.filterIsInstance<Button>().any { it.text == "Auftrag senden" && it.isEnabled } }
                waitFor { views ->
                    val scroll = views.filterIsInstance<android.widget.ScrollView>().first()
                    scroll.scrollY > 0 && !scroll.canScrollVertically(1)
                }
                scenario.onActivity { a ->
                    descendants(a.window.decorView).filterIsInstance<android.widget.ScrollView>().first().scrollTo(0, 0)
                }
                // An unchanged /status response must not reset text or undo a user's scroll.
                Thread.sleep(2000)
                scenario.onActivity { a ->
                    assertEquals(0, descendants(a.window.decorView).filterIsInstance<android.widget.ScrollView>().first().scrollY)
                }
                scenario.onActivity { a ->
                    val field = descendants(a.window.decorView).filterIsInstance<EditText>().single()
                    field.requestFocus()
                    (a.getSystemService(android.content.Context.INPUT_METHOD_SERVICE) as android.view.inputmethod.InputMethodManager)
                        .showSoftInput(field, android.view.inputmethod.InputMethodManager.SHOW_IMPLICIT)
                }
                waitFor { views ->
                    val field = views.filterIsInstance<EditText>().single()
                    val insets = field.rootWindowInsets
                    if (android.os.Build.VERSION.SDK_INT < 30 || insets == null ||
                        !insets.isVisible(android.view.WindowInsets.Type.ime())) false
                    else {
                        val bottom = field.rootView.height - insets.getInsets(android.view.WindowInsets.Type.ime()).bottom
                        val controls = listOf<View>(field) + views.filterIsInstance<Button>()
                            .filter { it.text == "Auftrag senden" || it.text == "Auftrag diktieren" }
                        controls.size == 3 && controls.all { view ->
                            val location = IntArray(2); view.getLocationInWindow(location)
                            view.isShown && view.height > 0 && location[1] + view.height <= bottom
                        }
                    }
                }
                scenario.onActivity { a ->
                    (a.getSystemService(android.content.Context.INPUT_METHOD_SERVICE) as android.view.inputmethod.InputMethodManager)
                        .hideSoftInputFromWindow(a.window.decorView.windowToken, 0)
                }
                val prompt = "Test only: \$(not-a-command); quote \"ok\""
                scenario.onActivity { a ->
                    val views = descendants(a.window.decorView)
                    views.filterIsInstance<EditText>().single().setText(prompt)
                    views.filterIsInstance<Button>().single { it.text == "Auftrag senden" }.performClick()
                }
                waitFor { views -> views.filterIsInstance<Button>().any { it.text == "Einmal erlauben" } }
                assertEquals(prompt, received.get().getString("text"))
                assertTrue(received.get().getString("requestId").matches(Regex("[0-9a-f]{32}")))
                scenario.onActivity { a ->
                    val views = descendants(a.window.decorView)
                    assertTrue(views.filterIsInstance<TextView>().any { it.text.toString().contains("Run public regression test") })
                    for (label in listOf("Einmal erlauben", "Ablehnen")) {
                        val choice = views.filterIsInstance<Button>().single { it.text == label }
                        val visible = android.graphics.Rect()
                        assertTrue("Permission must be reachable without scrolling", choice.getGlobalVisibleRect(visible))
                        assertEquals(choice.height, visible.height())
                    }
                    assertEquals(View.GONE, views.filterIsInstance<EditText>().single().visibility)
                    views.filterIsInstance<Button>().single { it.text == "Ablehnen" }.performClick()
                }
                waitFor { permission.get() != null }
                assertEquals("no", permission.get().getString("option"))
                assertEquals("fixture-permission", permission.get().getString("id"))
                waitFor { views -> views.filterIsInstance<EditText>().single().visibility == View.VISIBLE }
            }
        } finally {
            GeminiLocalSession.stop()
            running.set(false); server.close(); worker.join(2000)
        }
    }
}
