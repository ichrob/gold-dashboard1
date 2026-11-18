package ch.bob.degirocompanion

import android.os.PowerManager
import android.view.WindowManager
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

/** Local display-only test: no DEGIRO navigation, PIN entry or orders. */
@RunWith(AndroidJUnit4::class)
class BobScreenDemoUiTest {
    @Test fun demoHasTwoBoundedScreenHoldsAndReleasesOnStop() {
        ActivityScenario.launch(MainActivity::class.java).use { scenario ->
            scenario.onActivity { activity ->
                val start = MainActivity::class.java.getDeclaredMethod("startTradeScreenDemo")
                    .apply { isAccessible = true }
                val stop = MainActivity::class.java.getDeclaredMethod(
                    "stopTradeScreenDemo", String::class.java
                ).apply { isAccessible = true }
                val lease = MainActivity::class.java.getDeclaredField("demoWakeLease")
                    .apply { isAccessible = true }
                val active = MainActivity::class.java.getDeclaredField("demoActive")
                    .apply { isAccessible = true }
                val status = MainActivity::class.java.getDeclaredField("demoStatus")
                    .apply { isAccessible = true }

                start.invoke(activity)
                assertTrue(active.getBoolean(activity))
                val wakeLock = lease.get(activity) as PowerManager.WakeLock
                assertTrue("Screen-dim wake lease was not acquired", wakeLock.isHeld)
                assertTrue(
                    activity.window.attributes.flags and
                        WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON != 0
                )
                assertTrue((status.get(activity) as String).contains("20 Minuten"))

                stop.invoke(activity, "UI-Test abgeschlossen")
                assertFalse(active.getBoolean(activity))
                assertFalse("Leased wake lock was not released", wakeLock.isHeld)
                assertNull(lease.get(activity))
                assertEquals(0, activity.window.attributes.flags and
                    WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
                assertTrue((status.get(activity) as String).contains("UI-Test abgeschlossen"))
            }
        }
    }
}
