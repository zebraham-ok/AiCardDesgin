/**
 * AI 后台任务跟踪（用户 2026-09-27 定：**不在弹窗里干等**）。
 *
 * 交互约定：
 *   点「开始生成」→ 立即提交后端 job 并关掉弹窗 → 顶部通知告诉用户去哪拿结果；
 *   生成期间用户可以去干别的，完成后弹通知引导到「底板 → 从资源库中选择」
 *   或卡牌页的「从资源库选择」。
 *
 * 只跟踪"当前页面会话里发起过的任务"：刷新页面后跟踪丢失，
 * 但任务本身落盘在 `workspace/jobs/`，资源也确实已经进库了，不影响找回。
 */
import { ElNotification } from 'element-plus'
import { api } from '../api/client'

type Kind = 'baseplate' | 'cardart' | 'text'

interface Tracked {
  pid: string
  kind: Kind
  /** 模板名/卡名，用于通知文案 */
  label: string
  onDone?: (job: any) => void
}

const tracked = new Map<string, Tracked>()
let timer: number | undefined

/** 结果去哪找 —— 通知里必须说清楚，否则用户找不到图 */
function whereToFind(kind: Kind) {
  return kind === 'baseplate'
    ? '去模板编辑器工具栏的「底板」→「从资源库中选择」挑选'
    : '去卡牌编辑页对应字段的「从资源库选择」放进图片'
}

export function trackAiJob(jobId: string, opt: Tracked) {
  tracked.set(jobId, opt)
  ElNotification({
    title: '已转入后台生成',
    message: `预计 1–2 分钟。可以先去忙别的，完成后会通知你 —— ${whereToFind(opt.kind)}。`,
    type: 'info',
    duration: 8000
  })
  start()
}

function start() {
  if (timer) return
  timer = window.setInterval(tick, 4000)
}

async function tick() {
  if (!tracked.size) {
    window.clearInterval(timer)
    timer = undefined
    return
  }
  for (const [id, t] of [...tracked]) {
    try {
      const job = await api.get(`/ai/jobs/${id}`)
      if (!['done', 'error', 'canceled', 'interrupted'].includes(job.status)) continue
      tracked.delete(id)
      if (job.status === 'done') {
        ElNotification({
          title: `${t.label} · 生成完成（${job.images?.length || 0} 张）`,
          message: whereToFind(t.kind),
          type: 'success',
          duration: 12000
        })
      } else {
        ElNotification({
          title: `${t.label} · 生成未成功`,
          message: job.error || '可以再试一次',
          type: 'warning',
          duration: 10000
        })
      }
      t.onDone?.(job)
    } catch {
      tracked.delete(id)      // 查询失败（后端重启等）就放弃跟踪
    }
  }
}

/** 页面卸载时清掉定时器（插件式调用，避免内存泄漏） */
export function disposeAiJobsWatcher() {
  window.clearInterval(timer)
  timer = undefined
  tracked.clear()
}
