import { nextTick, onBeforeUnmount, watch, type Ref } from 'vue'

/**
 * 滚轮 / 触摸板缩放（模板编辑器与卡牌编辑器共用）。
 *
 * 两种手势：
 *  1. **Ctrl/⌘ + 滚轮**（触摸板双指捏合在浏览器里就是带 ctrlKey 的 wheel）→ 始终缩放。
 *  2. **普通滚轮** → 只有当画布在该方向**滚不动**时才用来缩放
 *     （画布比视口小的时候滚轮本来也没事干；一旦超出视口就恢复成滚动，
 *      免得想翻看长卡时莫名其妙在缩放）。
 *
 * 缩放锚定在**光标下的那个点**：缩放前后该点停在屏幕同一位置，
 * 不会"越缩越偏"。轴向上滚不动（画布比视口小）时不做锚定，交给居中对齐。
 */
export function useWheelZoom(opts: {
  stage: Ref<HTMLElement | undefined>
  zoom: Ref<number>
  min?: number
  max?: number
  /** 缩放变化后的收尾（Fabric 需要重设尺寸 + 重绘） */
  onZoom?: (z: number) => void
}) {
  const MIN = opts.min ?? 0.15
  const MAX = opts.max ?? 3
  const clamp = (z: number) => Math.min(MAX, Math.max(MIN, z))

  let bound: HTMLElement | null = null

  function onWheel(e: WheelEvent) {
    const stage = opts.stage.value
    const wrap = stage?.querySelector('.canvas-wrap') as HTMLElement | null
    if (!stage || !wrap) return

    const ctrl = e.ctrlKey || e.metaKey
    if (!ctrl) {
      // 普通滚轮：该方向还能滚就交给页面滚动
      const canScrollV = stage.scrollHeight - stage.clientHeight > 1
      const canScrollH = stage.scrollWidth - stage.clientWidth > 1
      const vertical = Math.abs(e.deltaY) >= Math.abs(e.deltaX)
      if ((vertical && canScrollV) || (!vertical && canScrollH)) return
    }

    // 按着修饰键就一律吃掉这个手势 —— 哪怕已经到缩放上下限，
    // 也不能让浏览器接管去做「缩放整个网页」
    if (ctrl) e.preventDefault()

    const z1 = opts.zoom.value
    // 指数缩放：触摸板捏合的 deltaY 很小，要平滑；鼠标滚轮一格 deltaY≈±100
    const z2 = clamp(z1 * Math.exp(-e.deltaY * (ctrl ? 0.0025 : 0.0015)))
    if (Math.abs(z2 - z1) < 1e-4) return
    e.preventDefault()

    // 光标对应的设计坐标（缩放前后要贴在同一个屏幕位置）
    const r1 = wrap.getBoundingClientRect()
    const cx = (e.clientX - r1.left) / z1
    const cy = (e.clientY - r1.top) / z1

    opts.zoom.value = z2
    opts.onZoom?.(z2)

    nextTick(() => {
      const r2 = wrap.getBoundingClientRect()
      const wantLeft = e.clientX - cx * z2
      const wantTop = e.clientY - cy * z2
      // scrollLeft 变大 = 内容左移，所以补偿量取反
      if (stage.scrollWidth - stage.clientWidth > 1) stage.scrollLeft -= wantLeft - r2.left
      if (stage.scrollHeight - stage.clientHeight > 1) stage.scrollTop -= wantTop - r2.top
    })
  }

  function bind(el?: HTMLElement) {
    if (bound === el) return
    bound?.removeEventListener('wheel', onWheel)
    bound = el || null
    // passive: false —— 要 preventDefault 掉浏览器自身的 Ctrl+滚轮页面缩放
    bound?.addEventListener('wheel', onWheel, { passive: false })
  }

  watch(opts.stage, (el) => bind(el), { immediate: true })
  onBeforeUnmount(() => bind(undefined))

  return { MIN, MAX }
}
