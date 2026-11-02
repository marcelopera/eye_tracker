package br.com.marcelopera.eye_tracking

import android.view.View
import android.widget.FrameLayout
import androidx.lifecycle.lifecycleScope
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import br.com.marcelopera.eye_tracking.session.TargetDisplay
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.launch
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class SessionDisplayTest {
    @Test
    fun targetsUseTheLaidOutSessionArea() {
        ActivityScenario.launch(MainActivity::class.java).use { scenario ->
            listOf(0.5 to 0.5, 0.1 to 0.1, 0.9 to 0.9).forEach { (x, y) ->
                val displayed = CountDownLatch(1)
                var result: TargetDisplay? = null
                scenario.onActivity { activity ->
                    activity.lifecycleScope.launch {
                        result = activity.showTarget(x, y)
                        displayed.countDown()
                    }
                }
                assertTrue("O alvo não foi exibido", displayed.await(5, TimeUnit.SECONDS))
                scenario.onActivity { activity ->
                    val root = activity.findViewById<FrameLayout>(android.R.id.content)
                        .getChildAt(0) as FrameLayout
                    val session = root.getChildAt(0) as FrameLayout
                    val dot: View = session.getChildAt(0)
                    val display = requireNotNull(result)
                    assertTrue(display.width > 0 && display.height > 0)
                    assertEquals(display.width, session.width)
                    assertEquals(display.height, session.height)
                    assertEquals((x * display.width).toFloat(), dot.x + dot.width / 2f, 1f)
                    assertEquals((y * display.height).toFloat(), dot.y + dot.height / 2f, 1f)
                }
            }
        }
    }
}
