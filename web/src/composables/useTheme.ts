import { computed, ref } from 'vue'

export type ThemeMode = 'light' | 'dark'

const STORAGE_KEY = 'bgw.theme'

// 模块级单例：所有组件共享同一份状态，切换后立即全局生效
const mode = ref<ThemeMode>('light')
const isDark = computed(() => mode.value === 'dark')

function apply(m: ThemeMode) {
  const el = document.documentElement
  // Element Plus 的暗色主题靠 html.dark 生效（dark/css-vars.css）
  el.classList.toggle('dark', m === 'dark')
  el.dataset.theme = m
  // 让滚动条、原生表单控件、autofill 等跟随主题
  el.style.colorScheme = m
}

function readSaved(): ThemeMode {
  try {
    const v = localStorage.getItem(STORAGE_KEY)
    if (v === 'dark' || v === 'light') return v
  } catch { /* 隐私模式下 localStorage 不可用 */ }
  return 'light'
}

function setMode(m: ThemeMode) {
  mode.value = m
  apply(m)
  try { localStorage.setItem(STORAGE_KEY, m) } catch { /* 忽略 */ }
}

/** 在 mount 之前调用，避免刷新时先亮后暗地闪一下 */
export function initTheme() {
  mode.value = readSaved()
  apply(mode.value)
}

export function useTheme() {
  return {
    mode,
    isDark,
    setMode,
    toggle: () => setMode(isDark.value ? 'light' : 'dark')
  }
}
