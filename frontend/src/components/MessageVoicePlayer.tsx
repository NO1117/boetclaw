import { Download, Pause, Play, Square } from 'lucide-react'
import {
  formatPlaybackTime,
  voiceModeLabel,
  type VoiceOutputMode,
  type VoicePlaybackProgress,
} from '../utils/voiceOutput'
import type { SpeechPlaybackState } from '../utils/speechOutput'
import './MessageVoicePlayer.css'

interface Props {
  mode: VoiceOutputMode
  state: SpeechPlaybackState
  progress: VoicePlaybackProgress
  providerLabel?: string | null
  onTogglePlay: () => void
  onStop: () => void
  onDownload: () => void
}

export default function MessageVoicePlayer({
  mode,
  state,
  progress,
  providerLabel,
  onTogglePlay,
  onStop,
  onDownload,
}: Props) {
  const ratio = progress.duration > 0 ? progress.current / progress.duration : 0
  const active = state === 'playing' || state === 'paused'

  return (
    <div className="message-voice-player" role="group" aria-label="回复语音播放器">
      <div className="message-voice-player-head">
        <span className="message-voice-mode">回复语音 · {voiceModeLabel(mode)}</span>
        {providerLabel && <span className="message-voice-provider mono">{providerLabel}</span>}
      </div>
      <div className="message-voice-track">
        <button
          type="button"
          className="message-voice-play-btn"
          aria-label={state === 'playing' ? '暂停' : '播放'}
          onClick={onTogglePlay}
        >
          {state === 'playing' ? <Pause size={14} /> : <Play size={14} />}
        </button>
        <div className="message-voice-progress" aria-hidden>
          <div className="message-voice-progress-fill" style={{ width: `${Math.round(ratio * 100)}%` }} />
        </div>
        <span className="message-voice-time mono">
          {formatPlaybackTime(progress.current)} / {formatPlaybackTime(progress.duration)}
        </span>
      </div>
      <div className="message-voice-actions">
        {active && (
          <button type="button" className="message-action-btn" onClick={onStop}>
            <Square size={14} /> 停止
          </button>
        )}
        {mode === 'server' && (
          <button type="button" className="message-action-btn" onClick={onDownload}>
            <Download size={14} /> 下载 MP3
          </button>
        )}
      </div>
    </div>
  )
}
