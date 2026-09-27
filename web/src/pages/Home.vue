<template>
  <div class="page">
    <div class="row" style="margin-bottom: 16px">
      <div>
        <h1 class="page-title">项目总览</h1>
        <div class="page-sub">共 {{ projects.length }} 个项目 · 数据目录 {{ wsPath }}</div>
      </div>
      <div class="spacer" />
      <el-input v-model="keyword" placeholder="搜索项目名 / 标签" clearable style="width: 220px" />
      <el-select v-model="sortBy" style="width: 130px">
        <el-option label="最近修改" value="updatedAt" />
        <el-option label="名称" value="name" />
        <el-option label="卡牌数" value="cardCount" />
      </el-select>
      <el-button type="primary" @click="showCreate = true">新建项目</el-button>
    </div>

    <div v-if="loading" class="empty">加载中…</div>

    <div v-else-if="!filtered.length" class="empty">
      还没有项目，点击右上角「新建项目」开始
    </div>

    <div v-else class="card-grid">
      <div v-for="p in filtered" :key="p.id" class="proj-card" @click="open(p.id)">
        <div class="thumb">
          <img v-if="p.cover" :src="resolveAsset(p.cover)" alt="" />
          <span v-else class="placeholder">🎴</span>
        </div>
        <div class="meta">
          <div class="name">
            {{ p.name }}
            <el-tag v-if="p.brief?.artStyle?.style" size="small" effect="plain" class="style-tag">
              {{ p.brief.artStyle.style }}
            </el-tag>
          </div>
          <!-- 优先用项目设定的「一句话卖点」（§4.4），没填才退回 description -->
          <div class="desc">{{ p.brief?.oneLiner || p.description || '暂无描述' }}</div>
          <div class="stats">
            <span>{{ p.templateCount }} 模板</span>
            <span>·</span>
            <span>{{ p.cardCount }} 卡牌</span>
            <span>·</span>
            <span>{{ fmt(p.updatedAt) }}</span>
          </div>
          <div v-if="tagList(p).length" class="tags">
            <el-tag v-for="t in tagList(p)" :key="t" size="small"
                    :effect="p.brief?.keywords?.length ? 'light' : 'plain'">{{ t }}</el-tag>
          </div>
        </div>
        <div class="ops" @click.stop>
          <el-dropdown trigger="click" @command="c => onCommand(c, p)">
            <el-button text size="small">⋯</el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="open">打开</el-dropdown-item>
                <el-dropdown-item command="rename">重命名</el-dropdown-item>
                <el-dropdown-item command="duplicate">复制项目</el-dropdown-item>
                <el-dropdown-item command="delete" divided>删除</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </div>
    </div>

    <el-dialog v-model="showCreate" title="新建项目" width="460">
      <el-form label-width="72px">
        <el-form-item label="名称"><el-input v-model="form.name" placeholder="例如：星域争霸" /></el-form-item>
        <el-form-item label="描述"><el-input v-model="form.description" type="textarea" :rows="2" /></el-form-item>
        <el-form-item label="标签"><el-input v-model="form.tagText" placeholder="逗号分隔，如：奇幻,核心" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreate = false">取消</el-button>
        <el-button type="primary" @click="create">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api, resolveAsset } from '../api/client'

const router = useRouter()
const projects = ref<any[]>([])
const loading = ref(true)
const keyword = ref('')
const sortBy = ref('updatedAt')
const wsPath = ref('')
const showCreate = ref(false)
const form = ref({ name: '', description: '', tagText: '' })

/** 卡片下方的 chips：优先展示项目设定的关键词（§4.4），没有则回退到项目标签 */
function tagList(p: any) {
  const kw = p.brief?.keywords || []
  return (kw.length ? kw.slice(0, 4) : (p.tags || []).slice(0, 4))
}

async function load() {
  loading.value = true
  try {
    projects.value = await api.get('/projects')
  } finally { loading.value = false }
}

const filtered = computed(() => {
  const k = keyword.value.trim().toLowerCase()
  let list = projects.value.filter(p =>
    !k || p.name.toLowerCase().includes(k) || (p.tags || []).join(',').toLowerCase().includes(k))
  if (sortBy.value === 'name') list = [...list].sort((a, b) => a.name.localeCompare(b.name, 'zh'))
  else if (sortBy.value === 'cardCount') list = [...list].sort((a, b) => b.cardCount - a.cardCount)
  else list = [...list].sort((a, b) => String(b.updatedAt).localeCompare(String(a.updatedAt)))
  return list
})

function fmt(t?: string) {
  if (!t) return '—'
  return String(t).slice(0, 16).replace('T', ' ')
}

function open(pid: string) { router.push(`/project/${pid}`) }

async function create() {
  if (!form.value.name.trim()) return ElMessage.warning('请填写项目名称')
  const tags = form.value.tagText.split(/[,，]/).map(s => s.trim()).filter(Boolean)
  const p = await api.post('/projects', { ...form.value, tags })
  showCreate.value = false
  form.value = { name: '', description: '', tagText: '' }
  ElMessage.success('已创建')
  router.push(`/project/${p.id}`)
}

async function onCommand(cmd: string, p: any) {
  if (cmd === 'open') return open(p.id)
  if (cmd === 'duplicate') {
    const np = await api.post(`/projects/${p.id}/duplicate`)
    ElMessage.success('已复制')
    await load()
    return
  }
  if (cmd === 'rename') {
    const { value } = await ElMessageBox.prompt('新名称', '重命名', { inputValue: p.name })
    if (value) { await api.patch(`/projects/${p.id}`, { name: value }); await load() }
    return
  }
  if (cmd === 'delete') {
    await ElMessageBox.confirm(`确定删除「${p.name}」？此操作不可撤销。`, '删除项目', { type: 'warning' })
    await api.del(`/projects/${p.id}`)
    ElMessage.success('已删除')
    await load()
  }
}

onMounted(async () => {
  await load()
  try { wsPath.value = (await api.get('/health')).workspace } catch { /* ignore */ }
})
</script>

<style scoped>
.proj-card {
  position: relative;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
  cursor: pointer;
  transition: box-shadow .15s, transform .15s;
}
.proj-card:hover { box-shadow: 0 6px 20px rgba(0, 0, 0, .08); transform: translateY(-2px); }

.thumb {
  height: 110px; background: var(--accent-soft);
  display: flex; align-items: center; justify-content: center;
}
.thumb img { width: 100%; height: 100%; object-fit: cover; }
.thumb .placeholder { font-size: 34px; opacity: .55; }

.meta { padding: 12px 14px 14px; }
.meta .name { font-weight: 700; font-size: 15px; margin-bottom: 4px; }
.meta .desc {
  color: var(--muted); font-size: 12px; min-height: 32px;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
.stats { display: flex; gap: 6px; font-size: 12px; color: var(--muted); margin-top: 8px; }
.style-tag { transform: scale(.85); margin-left: 4px; }
.tags { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 8px; }
.ops { position: absolute; top: 8px; right: 8px; }
</style>
