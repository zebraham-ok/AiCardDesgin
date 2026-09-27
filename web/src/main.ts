import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import zhCn from 'element-plus/es/locale/lang/zh-cn'

import App from './App.vue'
import { router } from './router'
import { warmupFonts } from './render/fonts'
import './styles.css'

// 预热自定义字体清单（只拉列表、不下载字体文件，真正用到时再按需注册）
warmupFonts().catch(() => { /* 后端未就绪时忽略 */ })

createApp(App)
  .use(createPinia())
  .use(router)
  .use(ElementPlus, { locale: zhCn })
  .mount('#app')
