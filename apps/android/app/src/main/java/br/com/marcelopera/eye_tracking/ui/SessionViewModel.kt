package br.com.marcelopera.eye_tracking.ui

import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import br.com.marcelopera.eye_tracking.session.SessionConfig
import br.com.marcelopera.eye_tracking.session.SessionPhase
import br.com.marcelopera.eye_tracking.session.SessionResult
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.receiveAsFlow

class SessionViewModel(
    private val savedStateHandle: SavedStateHandle,
) : ViewModel() {

    private val _uiState = MutableStateFlow(restoreState())
    val uiState: StateFlow<SessionUiState> = _uiState.asStateFlow()

    private val effectChannel = Channel<SessionEffect>(Channel.BUFFERED)
    val effects: Flow<SessionEffect> = effectChannel.receiveAsFlow()

    private var nextToken = 0L
    private var activeToken = -1L

    init {
        persist(_uiState.value)
    }

    val isCollecting: Boolean
        get() = _uiState.value.destination == Destination.Collecting

    fun onExperimentInputChanged(value: String) {
        val state = _uiState.value
        if (state.destination != Destination.Identification) return
        update(state.copy(experimentInput = value, idError = false))
    }

    fun continueFromIdentification() {
        val state = _uiState.value
        if (state.destination != Destination.Identification) return
        val experimentId = state.experimentInput.trim()
        if (experimentId.isEmpty()) {
            update(state.copy(idError = true))
            return
        }
        val changed = state.experimentId != experimentId
        update(
            state.copy(
                destination = Destination.Preparation,
                experimentInput = experimentId,
                experimentId = experimentId,
                videoUri = if (changed) null else state.videoUri,
                phase = SessionPhase.Idle,
                sessionId = null,
                notice = null,
                idError = false,
            ),
        )
    }

    fun onVideoSelected(uri: String) {
        val state = _uiState.value
        if (state.destination != Destination.Preparation) return
        update(state.copy(videoUri = uri, notice = null))
    }

    fun onVideoAccessChecked(uri: String, accessible: Boolean) {
        val state = _uiState.value
        if (state.destination != Destination.Preparation) return
        if (state.videoUri != uri || accessible) return
        update(state.copy(videoUri = null, notice = PreparationNotice.VideoAccessLost))
    }

    fun onStartClicked() {
        val state = _uiState.value
        if (state.destination != Destination.Preparation || state.phase != SessionPhase.Idle) {
            return
        }
        val experimentId = state.experimentId?.trim().orEmpty()
        if (experimentId.isEmpty()) {
            update(
                state.copy(
                    destination = Destination.Identification,
                    experimentInput = state.experimentInput,
                    idError = true,
                ),
            )
            return
        }
        if (state.videoUri == null) {
            update(state.copy(notice = PreparationNotice.VideoRequired))
            return
        }
        update(state.copy(phase = SessionPhase.AwaitingPermission, notice = null))
        effectChannel.trySend(SessionEffect.CheckCameraPermission)
    }

    fun onCameraPermissionResult(granted: Boolean) {
        val state = _uiState.value
        if (state.phase != SessionPhase.AwaitingPermission) return
        if (!granted) {
            update(state.copy(phase = SessionPhase.Idle, notice = PreparationNotice.CameraPermissionDenied))
            return
        }

        val experimentId = state.experimentId?.trim().orEmpty()
        val videoUri = state.videoUri
        if (experimentId.isEmpty() || videoUri == null) {
            update(
                state.copy(
                    phase = SessionPhase.Idle,
                    destination = if (experimentId.isEmpty()) Destination.Identification else Destination.Preparation,
                    idError = experimentId.isEmpty(),
                    notice = if (videoUri == null) PreparationNotice.VideoRequired else null,
                ),
            )
            return
        }

        activeToken = nextToken++
        update(
            state.copy(
                destination = Destination.Collecting,
                phase = SessionPhase.PreparingCamera,
                sessionId = null,
                notice = null,
            ),
        )
        effectChannel.trySend(
            SessionEffect.StartSession(
                token = activeToken,
                config = SessionConfig(experimentId, videoUri),
            ),
        )
    }

    fun acceptsStart(token: Long): Boolean {
        val state = _uiState.value
        return token == activeToken &&
            state.destination == Destination.Collecting &&
            state.phase == SessionPhase.PreparingCamera
    }

    fun onPhase(token: Long, phase: SessionPhase) {
        if (token != activeToken) return
        val state = _uiState.value
        if (state.destination != Destination.Collecting) return
        _uiState.value = state.copy(phase = phase)
    }

    fun onFinished(token: Long, result: SessionResult) {
        if (token != activeToken) return
        val state = _uiState.value
        if (state.destination != Destination.Collecting) return
        val next = when (result) {
            is SessionResult.Completed -> state.copy(
                destination = Destination.Completed,
                phase = SessionPhase.Completed,
                sessionId = result.sessionId,
                notice = null,
                idError = false,
            )

            is SessionResult.Interrupted -> state.copy(
                destination = Destination.Preparation,
                phase = SessionPhase.Idle,
                sessionId = null,
                notice = PreparationNotice.Interrupted,
            )

            is SessionResult.Failed -> state.copy(
                destination = Destination.Preparation,
                phase = SessionPhase.Idle,
                sessionId = null,
                notice = result.reason.toNotice(),
            )
        }
        update(next)
    }

    fun cancelPendingStart() {
        val state = _uiState.value
        if (state.destination != Destination.Collecting || state.phase != SessionPhase.PreparingCamera) return
        activeToken = nextToken++
        update(
            state.copy(
                destination = Destination.Preparation,
                phase = SessionPhase.Idle,
                sessionId = null,
                notice = PreparationNotice.Interrupted,
            ),
        )
    }

    fun backToIdentification() {
        val state = _uiState.value
        activeToken = nextToken++
        update(
            state.copy(
                destination = Destination.Identification,
                experimentInput = state.experimentId ?: state.experimentInput,
                phase = SessionPhase.Idle,
                sessionId = null,
                notice = null,
                idError = false,
            ),
        )
    }

    fun resetToIdentification() {
        activeToken = nextToken++
        update(SessionUiState(destination = Destination.Identification))
    }

    private fun update(state: SessionUiState) {
        _uiState.value = state
        persist(state)
    }

    private fun persist(state: SessionUiState) {
        savedStateHandle[KEY_INPUT] = state.experimentInput
        savedStateHandle[KEY_EXPERIMENT] = state.experimentId
        savedStateHandle[KEY_VIDEO] = state.videoUri
        savedStateHandle[KEY_DESTINATION] = state.destination.name
        savedStateHandle[KEY_SESSION] = state.sessionId
    }

    private fun restoreState(): SessionUiState {
        val input = savedStateHandle.get<String>(KEY_INPUT).orEmpty()
        val experimentId = savedStateHandle.get<String>(KEY_EXPERIMENT)
        val videoUri = savedStateHandle.get<String>(KEY_VIDEO)
        val sessionId = savedStateHandle.get<String>(KEY_SESSION)
        val savedDestination = savedStateHandle.get<String>(KEY_DESTINATION)
            ?.let { name -> runCatching { Destination.valueOf(name) }.getOrNull() }

        val interruptedWhileCollecting = savedDestination == Destination.Collecting
        val destination = when {
            interruptedWhileCollecting -> Destination.Preparation
            savedDestination == Destination.Completed && sessionId != null -> Destination.Completed
            savedDestination == Destination.Preparation -> Destination.Preparation
            else -> Destination.Identification
        }
        val phase = if (destination == Destination.Completed) {
            SessionPhase.Completed
        } else {
            SessionPhase.Idle
        }
        return SessionUiState(
            destination = destination,
            experimentInput = input,
            experimentId = experimentId,
            videoUri = videoUri,
            phase = phase,
            sessionId = if (destination == Destination.Completed) sessionId else null,
            notice = if (interruptedWhileCollecting) PreparationNotice.Interrupted else null,
        )
    }

    private companion object {
        const val KEY_INPUT = "experimentInput"
        const val KEY_EXPERIMENT = "experimentId"
        const val KEY_VIDEO = "videoUri"
        const val KEY_DESTINATION = "destination"
        const val KEY_SESSION = "sessionId"
    }
}
