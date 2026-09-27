/**
 * 吸附对齐 + 参考线。
 *
 * 拖动对象时把它吸附到：画布四边 / 画布中心 / 其他对象的边与中心，
 * 并实时画出对齐参考线（屏幕像素阈值，缩放后手感一致）。
 */
import { Canvas, Line } from 'fabric'

export interface SnapOptions {
  /** 画布内容尺寸（设计像素，不含缩放） */
  width: number
  height: number
  /** 当前缩放，用于把「屏幕像素阈值」换算成设计像素 */
  zoom: () => number
  /** 吸附开关 */
  enabled: () => boolean
  /** 吸附发生后的回调（可用于写回数据） */
  onSnap?: () => void
}

const GUIDE_COLOR = '#ff4d6d'

export function createSnapping(canvas: Canvas, opt: SnapOptions) {
  let guides: Line[] = []

  const clearGuides = () => {
    if (!guides.length) return
    canvas.remove(...guides)
    guides = []
  }

  const makeGuide = (x1: number, y1: number, x2: number, y2: number) => {
    const l = new Line([x1, y1, x2, y2], {
      stroke: GUIDE_COLOR,
      strokeWidth: 1,
      strokeUniform: true,
      selectable: false,
      evented: false,
      hoverCursor: 'default',
      data: { kind: 'snapGuide' }
    })
    guides.push(l)
    canvas.add(l)
    canvas.bringObjectToFront(l)
  }

  /** 收集候选对齐线：画布边/中心 + 其他对象的边/中心 */
  const candidates = (self: any) => {
    const v: number[] = [0, opt.width / 2, opt.width]
    const h: number[] = [0, opt.height / 2, opt.height]
    for (const o of canvas.getObjects()) {
      if (o === self || o.data?.kind === 'snapGuide' || o.data?.kind === 'guide') continue
      if (!o.visible) continue
      const r = o.getBoundingRect()
      v.push(r.left, r.left + r.width / 2, r.left + r.width)
      h.push(r.top, r.top + r.height / 2, r.top + r.height)
    }
    return { v, h }
  }

  const onMoving = (e: any) => {
    if (!opt.enabled()) { clearGuides(); return }
    const t = e.target
    if (!t) return
    clearGuides()

    const thr = 6 / (opt.zoom() || 1)
    const r = t.getBoundingRect()
    const { v, h } = candidates(t)

    let dx = 0, dy = 0
    let sx: number | null = null, sy: number | null = null

    // 竖直方向（x 轴对齐）：对象的 左 / 中 / 右
    const tvs: Array<[number, number]> = [
      [r.left, 0],
      [r.left + r.width / 2, r.width / 2],
      [r.left + r.width, r.width]
    ]
    let bestX = Infinity
    for (const [val, back] of tvs) {
      for (const c of v) {
        const d = c - (val + dx)
        if (Math.abs(d) < Math.min(thr, Math.abs(bestX))) {
          bestX = d
          sx = c - back
        }
      }
    }
    // 水平方向（y 轴对齐）
    const ths: Array<[number, number]> = [
      [r.top, 0],
      [r.top + r.height / 2, r.height / 2],
      [r.top + r.height, r.height]
    ]
    let bestY = Infinity
    for (const [val, back] of ths) {
      for (const c of h) {
        const d = c - (val + dy)
        if (Math.abs(d) < Math.min(thr, Math.abs(bestY))) {
          bestY = d
          sy = c - back
        }
      }
    }

    if (sx !== null || sy !== null) {
      // 换算成「对象左上角」的增量：bbox 左上角相对对象 left/top 的偏移
      const offX = r.left - (t.left ?? 0)
      const offY = r.top - (t.top ?? 0)
      if (sx !== null) t.set({ left: sx - offX })
      if (sy !== null) t.set({ top: sy - offY })
      t.setCoords()
      if (sx !== null) makeGuide(sx, 0, sx, opt.height)
      if (sy !== null) makeGuide(0, sy, opt.width, sy)
      opt.onSnap?.()
    }
    canvas.requestRenderAll()
  }

  canvas.on('object:moving', onMoving)
  canvas.on('mouse:up', clearGuides)
  canvas.on('object:modified', clearGuides)

  return {
    clear: clearGuides,
    dispose() {
      clearGuides()
      canvas.off('object:moving', onMoving)
      canvas.off('mouse:up', clearGuides)
      canvas.off('object:modified', clearGuides)
    }
  }
}
