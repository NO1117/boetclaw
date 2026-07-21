import { Loader2 } from 'lucide-react'
import {
  formatDurationMs,
  formatEstimatedCost,
  formatTokenCount,
  graphCacheLabel,
  type RunMetricsSummary,
} from '../utils/modelCapabilities'
import './RunMetricsCard.css'

interface Props {
  metrics: RunMetricsSummary | null
  loading?: boolean
  modelLabel?: string
}

function statusLabel(status?: string): { text: string; tone: 'done' | 'running' | 'idle' } {
  if (status === 'completed') return { text: '● 已完成', tone: 'done' }
  if (status === 'running') return { text: '● 运行中', tone: 'running' }
  if (status === 'interrupted') return { text: '● 已中断', tone: 'idle' }
  return { text: '● 待命', tone: 'idle' }
}

export default function RunMetricsCard({ metrics, loading, modelLabel }: Props) {
  const status = statusLabel(metrics?.status)
  const cacheText = graphCacheLabel(metrics?.graph_cache_hit)

  return (
    <div className="run-metrics-card context-card" aria-label="本次运行">
      <div className="run-metrics-header">本次运行</div>
      {modelLabel && <div className="run-metrics-model">{modelLabel}</div>}
      {loading && (
        <div className="run-metrics-loading" aria-busy="true">
          <Loader2 size={14} className="spin" />
          <span>采集中…</span>
        </div>
      )}
      {!loading && !metrics && (
        <p className="run-metrics-empty">暂无运行数据，发送消息后将展示耗时与 token 用量。</p>
      )}
      {metrics && (
        <>
          <div className={`run-metrics-status tone-${status.tone}`}>
            {status.text}   {cacheText}
          </div>
          <div className="run-metrics-section">
            <div className="run-metrics-label">响应耗时</div>
            <div className="run-metrics-value">
              首字 {formatDurationMs(metrics.time_to_first_token_ms)}
              {'     '}
              总计 {formatDurationMs(metrics.total_duration_ms)}
            </div>
          </div>
          <div className="run-metrics-section">
            <div className="run-metrics-label">TOKEN 用量</div>
            <div className="run-metrics-value">
              输入 {formatTokenCount(metrics.input_tokens)}
              {'     '}
              输出 {formatTokenCount(metrics.output_tokens)}
            </div>
          </div>
          <div className="run-metrics-section">
            <div className="run-metrics-label">估算费用</div>
            <div className="run-metrics-value cost">{formatEstimatedCost(metrics)}</div>
          </div>
          <div className="run-metrics-footnote">
            {(metrics.attachment_count ?? 0) > 0
              ? `${metrics.attachment_count} 个附件`
              : '无附件'}
            {(metrics.retrieval_hits ?? 0) > 0 ? ` · ${metrics.retrieval_hits} 条检索命中` : ''}
            {metrics.trace_id ? `\nTrace ${metrics.trace_id.slice(0, 4)}…${metrics.trace_id.slice(-4)}` : ''}
          </div>
        </>
      )}
    </div>
  )
}
