<template>
  <div class="app-shell">
    <header class="topbar">
      <div class="brand" @click="router.push('/')">
        <span class="logo">🎴</span>
        <span class="name">桌游设计工作坊</span>
      </div>
      <el-breadcrumb separator="/" class="crumbs">
        <el-breadcrumb-item :to="{ path: '/' }">首页</el-breadcrumb-item>
        <el-breadcrumb-item v-if="projectName">{{ projectName }}</el-breadcrumb-item>
      </el-breadcrumb>
      <div class="spacer" />
      <el-radio-group v-model="themeMode" size="small" class="theme-switch">
        <el-radio-button value="light" title="亮色模式">亮色</el-radio-button>
        <el-radio-button value="dark" title="暗色模式">暗色</el-radio-button>
      </el-radio-group>
      <el-button text @click="router.push('/assets')">资源管理</el-button>
      <el-tag v-if="health" size="small" type="info" effect="plain">
        {{ health.workspace }}
      </el-tag>
    </header>
    <main class="content">
      <router-view />
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from './api/client'
import { useTheme, type ThemeMode } from './composables/useTheme'

const router = useRouter()
const route = useRoute()
const health = ref<any>(null)
const projectName = ref('')

// 顶栏亮/暗切换：状态与持久化都在 useTheme 里，这里只做双向绑定
const { mode, setMode } = useTheme()
const themeMode = computed<ThemeMode>({
  get: () => mode.value,
  set: v => setMode(v)
})

async function loadProjectName() {
  const pid = route.params.pid as string
  if (!pid) { projectName.value = ''; return }
  try {
    const p = await api.get(`/projects/${pid}`)
    projectName.value = p.name
  } catch { projectName.value = '' }
}

onMounted(async () => {
  try { health.value = await api.get('/health') } catch { /* 后端未起 */ }
  loadProjectName()
})
watch(() => route.params.pid, loadProjectName)
</script>

<style scoped>
.app-shell { display: flex; flex-direction: column; height: 100%; }

.topbar {
  display: flex; align-items: center; gap: 16px;
  height: 52px; padding: 0 20px; flex: none;
  background: var(--panel); border-bottom: 1px solid var(--border);
}

.brand { display: flex; align-items: center; gap: 8px; cursor: pointer; }
.brand .logo { font-size: 20px; }
.brand .name { font-weight: 700; font-size: 15px; }
.crumbs { font-size: 13px; }
.theme-switch { flex: none; }
.content { flex: 1; overflow: auto; }
</style>
