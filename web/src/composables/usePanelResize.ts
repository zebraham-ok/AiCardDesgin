import { ref } from 'vue'

/**
 * 左右侧栏拖拽调宽（模板编辑器 / 卡牌编辑器共用）。
 *
 * 用 pointer 事件 + `setPointerCapture`：拖到元素外面也不会丢事件，
 * 不用往 window 上挂全局监听。宽度存 `localStorage`（下次进来还是你调过的宽度），
 * 双击抓手恢复默认值。
 *
 * 用法（放在页面 setup 里）：
 * ```ts
 * const { width: leftW, onDown: dragLeft, reset: resetLeft } = usePanelResize('tplLeft', 270)
 * ```
 * ```html
 * <aside class="side left" :style="{ width: leftW + 'px' }">…</aside>
 * <div class="grip" @pointerdown="e => dragLeft(e, 1)" @dblclick="resetLeft()" />
 * ```
 * `dir` 是拖动方向：左侧栏 +1（往右变宽），右侧栏 -1（往左变宽）。
 */
export function usePanelResize(key: string, def: number, min = 200, max = 560) {
  const storeKey = `bgw.panel.${key}`

  function clamp(v: number) {
    return Math.round(Math.min(max, Math.max(min, v)))
  }

  const saved = Number(localStorage.getItem(storeKey))
  // 存过的值可能来自更小/更大的窗口，读回来也要夹一次
  const width = ref(saved > 0 ? clamp(saved) : def)

  function onDown(e: PointerEvent, dir: 1 | -1) {
    const el = e.currentTarget as HTMLElement
    const startX = e.clientX
    const startW = width.value
    const prevCursor = document.body.style.cursor
    const prevSelect = document.body.style.userSelect
    el.setPointerCapture(e.pointerId)
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'      // 拖动时别顺手选中面板里的文字

    const move = (ev: PointerEvent) => {
      width.value = clamp(startW + dir * (ev.clientX - startX))
    }
    const up = () => {
      try { el.releasePointerCapture(e.pointerId) } catch { /* 已释放 */ }
      el.removeEventListener('pointermove', move)
      el.removeEventListener('pointerup', up)
      el.removeEventListener('pointercancel', up)
      document.body.style.cursor = prevCursor
      document.body.style.userSelect = prevSelect
      localStorage.setItem(storeKey, String(width.value))
    }
    el.addEventListener('pointermove', move)
    el.addEventListener('pointerup', up)
    el.addEventListener('pointercancel', up)
  }

  function reset() {
    width.value = def
    localStorage.setItem(storeKey, String(def))
  }

  return { width, onDown, reset }
}
