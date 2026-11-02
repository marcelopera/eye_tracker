package br.com.marcelopera.eye_tracking

import androidx.lifecycle.SavedStateHandle
import br.com.marcelopera.eye_tracking.session.SessionPhase
import br.com.marcelopera.eye_tracking.session.SessionResult
import br.com.marcelopera.eye_tracking.ui.Destination
import br.com.marcelopera.eye_tracking.ui.PreparationNotice
import br.com.marcelopera.eye_tracking.ui.SessionEffect
import br.com.marcelopera.eye_tracking.ui.SessionViewModel
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class SessionViewModelTest {

    @Test
    fun blankIdDoesNotAdvance() {
        val viewModel = SessionViewModel(SavedStateHandle())

        viewModel.onExperimentInputChanged("   ")
        viewModel.continueFromIdentification()

        assertEquals(Destination.Identification, viewModel.uiState.value.destination)
        assertTrue(viewModel.uiState.value.idError)
    }

    @Test
    fun missingVideoBlocksStart() {
        val viewModel = preparedViewModel()

        viewModel.onStartClicked()

        assertEquals(SessionPhase.Idle, viewModel.uiState.value.phase)
        assertEquals(PreparationNotice.VideoRequired, viewModel.uiState.value.notice)
    }

    @Test
    fun validPreparationRequestsPermissionThenStarts() = runTest {
        val viewModel = preparedViewModel()
        viewModel.onVideoSelected(VIDEO_URI)

        viewModel.onStartClicked()

        assertEquals(SessionPhase.AwaitingPermission, viewModel.uiState.value.phase)
        assertEquals(SessionEffect.CheckCameraPermission, viewModel.effects.first())

        viewModel.onCameraPermissionResult(true)

        assertEquals(Destination.Collecting, viewModel.uiState.value.destination)
        assertEquals(SessionPhase.PreparingCamera, viewModel.uiState.value.phase)
        val effect = viewModel.effects.first() as SessionEffect.StartSession
        assertEquals(EXPERIMENT_ID, effect.config.experimentId)
        assertEquals(VIDEO_URI, effect.config.videoUri)
        assertTrue(viewModel.acceptsStart(effect.token))
    }

    @Test
    fun deniedPermissionReturnsToPreparation() = runTest {
        val viewModel = preparedWithVideoViewModel()
        viewModel.onStartClicked()
        viewModel.effects.first()

        viewModel.onCameraPermissionResult(false)

        assertEquals(Destination.Preparation, viewModel.uiState.value.destination)
        assertEquals(SessionPhase.Idle, viewModel.uiState.value.phase)
        assertEquals(
            PreparationNotice.CameraPermissionDenied,
            viewModel.uiState.value.notice,
        )
    }

    @Test
    fun preparationSurvivesRecreation() {
        val savedState = SavedStateHandle()
        val first = SessionViewModel(savedState)
        first.onExperimentInputChanged(EXPERIMENT_ID)
        first.continueFromIdentification()
        first.onVideoSelected(VIDEO_URI)

        val restored = SessionViewModel(savedState)

        assertEquals(Destination.Preparation, restored.uiState.value.destination)
        assertEquals(EXPERIMENT_ID, restored.uiState.value.experimentId)
        assertEquals(VIDEO_URI, restored.uiState.value.videoUri)
        assertNull(restored.uiState.value.notice)
    }

    @Test
    fun collectingRestoredAfterProcessDeathBecomesInterruptedPreparation() = runTest {
        val savedState = SavedStateHandle()
        val first = SessionViewModel(savedState)
        first.onExperimentInputChanged(EXPERIMENT_ID)
        first.continueFromIdentification()
        first.onVideoSelected(VIDEO_URI)
        first.onStartClicked()
        first.effects.first()
        first.onCameraPermissionResult(true)
        first.effects.first()

        val restored = SessionViewModel(savedState)

        assertEquals(Destination.Preparation, restored.uiState.value.destination)
        assertEquals(SessionPhase.Idle, restored.uiState.value.phase)
        assertEquals(PreparationNotice.Interrupted, restored.uiState.value.notice)
    }

    @Test
    fun staleSessionCallbacksAreIgnored() = runTest {
        val viewModel = preparedWithVideoViewModel()
        viewModel.onStartClicked()
        viewModel.effects.first()
        viewModel.onCameraPermissionResult(true)
        val start = viewModel.effects.first() as SessionEffect.StartSession

        viewModel.onFinished(start.token + 1, SessionResult.Completed("old-session"))

        assertEquals(Destination.Collecting, viewModel.uiState.value.destination)
        assertNull(viewModel.uiState.value.sessionId)
    }

    @Test
    fun completedSessionIsShownOnlyAfterFinishedCallback() = runTest {
        val viewModel = preparedWithVideoViewModel()
        viewModel.onStartClicked()
        viewModel.effects.first()
        viewModel.onCameraPermissionResult(true)
        val start = viewModel.effects.first() as SessionEffect.StartSession

        viewModel.onPhase(start.token, SessionPhase.Finalizing)
        assertEquals(Destination.Collecting, viewModel.uiState.value.destination)
        assertEquals(SessionPhase.Finalizing, viewModel.uiState.value.phase)

        viewModel.onFinished(start.token, SessionResult.Completed("session-1"))

        assertEquals(Destination.Completed, viewModel.uiState.value.destination)
        assertEquals(SessionPhase.Completed, viewModel.uiState.value.phase)
        assertEquals("session-1", viewModel.uiState.value.sessionId)
    }

    @Test
    fun inaccessibleVideoIsCleared() {
        val viewModel = preparedWithVideoViewModel()

        viewModel.onVideoAccessChecked(VIDEO_URI, false)

        assertNull(viewModel.uiState.value.videoUri)
        assertEquals(PreparationNotice.VideoAccessLost, viewModel.uiState.value.notice)
    }

    private fun preparedViewModel(): SessionViewModel =
        SessionViewModel(SavedStateHandle()).apply {
            onExperimentInputChanged(EXPERIMENT_ID)
            continueFromIdentification()
        }

    private fun preparedWithVideoViewModel(): SessionViewModel =
        preparedViewModel().apply { onVideoSelected(VIDEO_URI) }

    private companion object {
        const val EXPERIMENT_ID = "exp-123"
        const val VIDEO_URI = "content://videos/stimulus.mp4"
    }
}
