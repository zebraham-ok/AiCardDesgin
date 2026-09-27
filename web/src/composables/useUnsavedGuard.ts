import { onBeforeUnmount, onMounted } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { ElMessageBox } from 'element-plus'

/**
 * 未保存改动的离开保护。
 *
 * 两条路径分开处理，因为浏览器给的能力不一样：
 *  1. **站内跳转**（返回项目 / 回首页 / 点另一张卡）：自定义三选弹窗
 *     —— 「保存并离开」/「不保存」/「取消」（右上角 × 也算取消）。
 *  2. **关闭或刷新标签页**：只能用浏览器原生确认框（`beforeunload`），
 *     文案由浏览器写死，不允许自定义，也**无法提供「保存」**（异步保存来不及完成）。
 *
 * 用法（放在页面 setup 里）：
 * ```ts
 * useUnsavedGuard(() => dirty.value, save)
 * ```
 * 保存失败时返回 false 留在原页，不会静默丢数据。
 */
export function useUnsavedGuard(isDirty: () => boolean, save: () => Promise<unknown>) {
  function onBeforeUnload(e: BeforeUnloadEvent) {
    if (!isDirty()) return
    e.preventDefault()
    e.returnValue = ''            // Chrome 必须设置 returnValue 才会弹原生确认
  }

  onMounted(() => window.addEventListener('beforeunload', onBeforeUnload))
  onBeforeUnmount(() => window.removeEventListener('beforeunload', onBeforeUnload))

  onBeforeRouteLeave(async () => {
    if (!isDirty()) return true
    try {
      await ElMessageBox.confirm('当前改动还没保存，离开就会丢失。', '有未保存的改动', {
        confirmButtonText: '保存并离开',
        cancelButtonText: '不保存',
        distinguishCancelAndClose: true,   // 区分「不保存」与「关闭弹窗」
        type: 'warning'
      })
      await save()
      return true
    } catch (e) {
      // 'cancel' = 明确选了不保存；'close' = 关掉弹窗；其他 = save() 抛错
      if (e === 'cancel') return true
      return false
    }
  })
}
