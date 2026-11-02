package validacao.mvvm

import br.com.marcelopera.eye_tracking.data.SessionEvent
import br.com.marcelopera.eye_tracking.data.SessionHandle
import br.com.marcelopera.eye_tracking.data.SessionStore
import br.com.marcelopera.eye_tracking.session.*
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runTest
import java.io.File
import kotlin.coroutines.resume

/** Reproduções de diagnóstico; não integram a suíte normal nem executam a UI Android. */
@OptIn(ExperimentalCoroutinesApi::class)
fun main() {
    runBlocking {
        var failure: Throwable? = null
        suspendCancellableCoroutine<Unit> { continuation ->
            // Mesma dupla inscrição usada em MainActivity.showTarget.
            continuation.invokeOnCancellation { }
            try {
                continuation.invokeOnCancellation { }
            } catch (error: Throwable) {
                failure = error
            }
            continuation.resume(Unit)
        }
        check(failure is IllegalStateException)
        println("P1 REPRODUZIDO: ${failure!!::class.simpleName}: ${failure.message}")
    }

    runTest {
        var savedEvents = emptyList<SessionEvent>()
        var finishedResult: SessionResult? = null
        val phases = mutableListOf<SessionPhase>()
        val videoEnd = CompletableDeferred<VideoPlayback>()
        val host = object : SessionHost {
            override suspend fun showPreparing() = Unit
            override suspend fun showMarker(flashOn: Boolean) = 10L
            override suspend fun showTarget(x: Double, y: Double) = TargetDisplay(20L, 1080, 1920)
            override suspend fun showRest() = 30L
            override suspend fun playVideo(uri: String): VideoPlayback = videoEnd.await()
            override suspend fun showFinalizing() = Unit
        }
        val store = object : SessionStore {
            override suspend fun createSession(experimentId: String) =
                SessionHandle("diagnostico", File("diretorio-ficticio-nao-criado"))

            override suspend fun save(
                handle: SessionHandle,
                experimentId: String,
                completed: Boolean,
                events: List<SessionEvent>,
            ): Boolean {
                savedEvents = events.toList()
                return true
            }
        }
        val recording = object : Recording {
            override suspend fun awaitStart() = true
            override suspend fun stopAndAwaitFinalize() = FinalizeInfo(false, 0)
            override fun unbind() = Unit
        }
        val controller = SessionController(
            store = store,
            listener = object : SessionController.Listener {
                override fun onPhase(token: Long, phase: SessionPhase) { phases += phase }
                override fun onFinished(token: Long, result: SessionResult) { finishedResult = result }
            },
            recordingEngines = RecordingEngineFactory { RecordingEngine { recording } },
            scope = this,
            timeSource = { testScheduler.currentTime * 1_000_000L },
        )
        controller.attachHost(host)
        controller.start(SessionConfig("experimento", "content://video"), 1L)
        advanceUntilIdle()
        check(phases.last() == SessionPhase.Stimulus)
        controller.interrupt()
        advanceUntilIdle()
        check(finishedResult is SessionResult.Interrupted)
        check(savedEvents.any { it.name == "interrompida" })
        check(savedEvents.none { it.name == "estimulo_inicio" })
        println("P2 REPRODUZIDO: metadados sem estimulo_inicio ao interromper na fase Stimulus.")
        println("Eventos finais: ${savedEvents.takeLast(4).map { it.name }}")
    }
}
