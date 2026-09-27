<template>
  <div class="page">
    <div class="row" style="margin-bottom: 14px">
      <div>
        <h1 class="page-title">资源管理</h1>
        <div class="page-sub">全局共享 · icon 子库 / 字体 / 图片 / 底板</div>
      </div>
      <div class="spacer" />
      <el-button @click="router.push('/')">返回首页</el-button>
    </div>

    <el-tabs v-model="tab" @tab-change="load">
      <el-tab-pane label="Icon 库" name="icon" />
      <el-tab-pane label="字体" name="font" />
      <el-tab-pane label="图片" name="image" />
      <el-tab-pane label="底板" name="baseplate" />
    </el-tabs>

    <div class="row" style="margin-bottom: 12px">
      <el-select v-if="tab === 'icon'" v-model="lib" style="width: 150px" @change="load">
        <el-option label="全部子库" value="" />
        <el-option v-for="l in libs" :key="l.id" :label="`${l.name} (${l.count})`" :value="l.id" />
      </el-select>
      <el-input v-model="q" placeholder="搜索名称 / 标签" clearable style="width: 200px" @input="load" />
      <div class="spacer" />
      <el-button type="primary" @click="fileEl?.click()">上传</el-button>
    </div>

    <div v-if="!items.length" class="empty">暂无资源</div>

    <div v-else-if="tab === 'icon'" class="icon-grid">
      <div v-for="a in items" :key="a.id" class="icon-cell">
        <img :src="resolveAsset(a.id)" />
        <span>{{ a.name }}</span>
        <span class="muted lib">{{ libName(a.library) }}</span>
        <el-button text size="small" type="danger" @click="remove(a)">删除</el-button>
      </div>
    </div>

    <div v-else class="card-grid">
      <div v-for="a in items" :key="a.id" class="panel asset-card">
        <div class="thumb">
          <!-- 用缩略图：底板原图 1–2 MB，列表里几十张会白等好久 -->
          <img v-if="tab === 'image' || tab === 'baseplate'" :src="thumbUrl(a.id)" />
          <span v-else class="font-sample" :style="{ fontFamily: familyOf(a) }">Aa 卡牌 123</span>
        </div>
        <div class="name">{{ a.name }}</div>
        <div v-if="tab === 'font'" class="muted" style="font-size:11px">
          {{ fontState(a) }}
        </div>
        <div class="muted" style="font-size:12px">{{ Math.round(a.size / 1024) }} KB</div>
        <el-button text size="small" type="danger" @click="remove(a)">删除</el-button>
      </div>
    </div>

    <input ref="fileEl" type="file" hidden @change="onFile" />

    <!-- 图片 / 底板先裁切再入库（自由比例，可切 1:1 / 16:9 等预设） -->
    <ImageCropDialog v-model="showCrop" :file="cropFile" @cropped="onCropped" />
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api, thumbUrl } from '../api/client'
import ImageCropDialog from '../components/ImageCropDialog.vue'
import { familyOf, ensureFamily, fontError, isFontRegistered, refreshFontList } from '../render/fonts'

const router = useRouter()
const tab = ref('icon')
const lib = ref('')
const q = ref('')
const libs = ref<any[]>([])
const items = ref<any[]>([])
const fileEl = ref<HTMLInputElement>()
/** 字体注册状态存在模块级 Set 里，不是响应式的；靠这个计数触发预览重渲染 */
const fontTick = ref(0)

const accept: Record<string, string> = {
  icon: '.svg', font: '.ttf,.otf,.woff2',
  image: 'image/*', baseplate: 'image/*'
}

async function load() {
  libs.value = await api.get('/asset-libraries')
  const p = new URLSearchParams({ type: tab.value })
  if (lib.value) p.set('library', lib.value)
  if (q.value) p.set('q', q.value)
  items.value = await api.get(`/assets?${p}`)
  if (tab.value === 'font') await loadFonts()
}

/** 字体 tab：逐个注册（FontFace），注册成功的预览才是真字形，否则会静默回退 */
async function loadFonts() {
  await refreshFontList(true)
  for (const a of items.value) {
    await ensureFamily(familyOf(a))
    fontTick.value++          // 注册状态是模块级的 Set，靠这个计数触发重渲染
  }
}

function fontState(a: any) {
  void fontTick.value
  const f = familyOf(a)
  if (isFontRegistered(f)) return '已载入画布可用'
  return fontError(f) ? `载入失败：${fontError(f)}` : '正在载入…'
}

function libName(id: string) {
  return libs.value.find((l: any) => l.id === id)?.name || id || '—'
}

const cropFile = ref<File | null>(null)
const showCrop = ref(false)

async function onFile(e: Event) {
  const el = e.target as HTMLInputElement
  const file = el.files?.[0]
  el.value = ''
  if (!file) return
  // 图片与底板先裁切（icon 是 SVG、字体是二进制，都直接传）
  if (tab.value === 'image' || tab.value === 'baseplate') {
    cropFile.value = file
    showCrop.value = true
    return
  }
  await uploadFile(file)
}

/** 真正上传。裁切后走这里时传的是新的 PNG File */
async function uploadFile(file: File) {
  const form = new FormData()
  form.append('file', file)
  form.append('type', tab.value)
  if (tab.value === 'icon' && lib.value) form.append('library', lib.value)
  await api.upload('/assets/upload', form)
  if (tab.value === 'font') await refreshFontList(true)
  ElMessage.success('已上传')
  await load()
}

async function onCropped(blob: Blob) {
  const name = (cropFile.value?.name || 'image').replace(/\.[^.]+$/, '')
  await uploadFile(new File([blob], `${name}.png`, { type: 'image/png' }))
}

async function remove(a: any) {
  await ElMessageBox.confirm(`删除「${a.name}」？`, '提示', { type: 'warning' })
  await api.del(`/assets/${a.id}`)
  load()
}

onMounted(load)
</script>

<style scoped>
.icon-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(96px, 1fr)); gap: 10px;
}
.icon-cell {
  background: #fff; border: 1px solid var(--border); border-radius: 8px;
  padding: 10px 6px; text-align: center;
}
.icon-cell img { width: 38px; height: 38px; }
.icon-cell span { display: block; font-size: 12px; margin-top: 4px; }
.icon-cell .lib { font-size: 11px; }
.asset-card .thumb {
  height: 90px; background: #f5f6f8; display: flex;
  align-items: center; justify-content: center; margin-bottom: 8px; overflow: hidden;
}
.asset-card img { max-width: 100%; max-height: 100%; object-fit: contain; }
.font-sample { font-size: 22px; }
.asset-card .name { font-weight: 600; font-size: 13px; }
</style>
