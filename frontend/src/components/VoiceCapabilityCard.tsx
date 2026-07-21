import { useEffect, useState } from 'react'
import { fetchVoiceCapabilities, type VoiceCapabilities } from '../services/api'
import { getSpeechRecognitionCtor } from '../utils/speechInput'
import { isSpeechSynthesisSupported } from '../utils/speechOutput'
import './MessageVoicePlayer.css'

function statusLabel(status: string): string {
  switch (status) {
    case 'configured': return '● 服务端已配置'
    case 'unconfigured': return '○ 服务端未配置'
    case 'unavailable': return '● 服务端不可用'
    default: return '● 服务端状态未知'
  }
}

function statusClass(status: string): string {
  if (status === 'configured') return 'ok'
  if (status === 'unconfigured') return 'warn'
  return 'off'
}

export default function VoiceCapabilityCard() {
  const [caps, setCaps] = useState<VoiceCapabilities | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    void (async () => {
      try {
        setCaps(await fetchVoiceCapabilities())
      } catch (e) {
        setError(String(e))
      }
    })()
  }, [])

  const browserStt = getSpeechRecognitionCtor() ? '可用' : '不可用'
  const browserTts = isSpeechSynthesisSupported() ? '可用' : '不可用'

  return (
    <div className="voice-capability-card" aria-label="语音能力状态">
      <h4>语音能力</h4>
      {error && <p className="voice-capability-note">{error}</p>}
      {caps && (
        <>
          <p className={`voice-capability-status ${statusClass(caps.stt.status)}`}>
            {statusLabel(caps.stt.status)}
          </p>
          <p className="voice-capability-detail">
            {`转写  ${caps.stt.model ?? '—'}\n合成  ${caps.tts.model ?? '—'}${caps.tts.voice ? ` · ${caps.tts.voice}` : ''}\n格式  ${caps.stt.formats.join(' · ').toUpperCase()}`}
          </p>
          <p className="voice-capability-note voice-capability-status warn">
            录音临时处理，请求结束即清理
          </p>
        </>
      )}
      <p className="voice-capability-detail">
        {`浏览器识别  ${browserStt}\n浏览器朗读  ${browserTts}`}
      </p>
      <p className="voice-capability-note">浏览器本地模式可作为降级；密钥不在此展示。</p>
    </div>
  )
}
