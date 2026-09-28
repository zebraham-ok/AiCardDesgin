import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
// Element Plus 暗色变量（必须排在 index.css 之后），配合 html.dark 生效
import 'element-plus/theme-chalk/dark/css-vars.css'
import zhCn from 'element-plus/es/locale/lang/zh-cn'

import App from './App.vue'
import { router } from './router'
import { warmupFonts } from './render/fonts'
import { initTheme } from './composables/useTheme'
import './styles.css'

// 先定主题再挂载，避免刷新时闪一下亮色
initTheme()

// 预热自定义字体清单（只拉列表、不下载字体文件，真正用到时再按需注册）
warmupFonts().catch(() => { /* 后端未就绪时忽略 */ })

createApp(App)
  .use(createPinia())
  .use(router)
  .use(ElementPlus, { locale: zhCn })
  .mount('#app')
