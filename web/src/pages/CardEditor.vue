<template>
  <div class="editor" v-loading="loading">
    <div class="toolbar">
      <el-button size="small" @click="router.back()">返回项目</el-button>
      <el-tag size="small" type="info">{{ tpl?.name || '—' }}</el-tag>

      <el-radio-group v-model="mode" size="small" @change="onModeChange">
        <el-radio-button value="form">表单模式</el-radio-button>
        <el-radio-button value="table">表格批量模式</el-radio-button>
      </el-radio-group>

      <template v-if="mode === 'table'">
        <el-select v-model="tableTplId" size="small" style="width:160px" @change="loadTable">
          <el-option v-for="t in templates" :key="t.id" :label="t.name" :value="t.id" />
        </el-select>
        <el-input v-model="tableQ" size="small" style="width:150px" placeholder="过滤卡名"
                  clearable @input="loadTable" />
        <el-button size="small" type="primary" :disabled="!editCount" @click="saveTable">
          保存 {{ editCount }} 处修改
        </el-button>
      </template>

      <div class="spacer" />
      <el-button v-if="mode === 'form'" size="small" @click="openNewCard">＋新建卡牌</el-button>
      <el-button size="small" @click="showImport = true">导入</el-button>
      <el-button v-if="mode === 'form' && card" size="small" @click="showExport = true">
        导出这张（图片/PDF）
      </el-button>
      <el-dropdown size="small" @command="exportData">
        <el-button size="small">导出数据 ▾</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="csv">卡牌数据 CSV</el-dropdown-item>
            <el-dropdown-item command="json">卡牌数据 JSON</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <el-button-group v-if="mode === 'form'">
        <el-button size="small" title="缩小（Ctrl/⌘ + 滚轮，或触摸板双指捏合）"
                   @click="zoom = Math.max(0.2, +(zoom - 0.1).toFixed(2))">－</el-button>
        <el-button size="small" title="适应窗口" @click="fitZoom">{{ Math.round(zoom * 100) }}%</el-button>
        <el-button size="small" title="放大（Ctrl/⌘ + 滚轮，或触摸板双指捏合）"
                   @click="zoom = Math.min(3, +(zoom + 0.1).toFixed(2))">＋</el-button>
      </el-button-group>
      <el-button v-if="mode === 'form'" size="small" type="primary" :disabled="!dirty" @click="save">保存</el-button>
    </div>

    <div class="body">
      <!-- 左：卡列表 -->
      <aside class="side left" :style="{ width: leftW + 'px' }">
        <div style="padding: 8px">
          <el-input v-model="q" size="small" placeholder="搜索卡名" clearable @input="loadList" />
        </div>
        <el-scrollbar>
          <div
            v-for="c in list" :key="c.id"
            class="item" :class="{ active: c.id === card?.id }"
            @click="open(c.id)">
            <span class="cname">{{ c.name }}</span>
            <span class="muted" style="font-size:11px">{{ tplName(c.templateId) }}</span>
          </div>
          <div v-if="!list.length" class="empty" style="padding:20px 8px">没有卡牌</div>
        </el-scrollbar>
      </aside>

      <!-- 拖动调宽（双击恢复默认） -->
      <div class="grip" title="拖动调宽 · 双击恢复默认"
           @pointerdown="(e: PointerEvent) => dragLeft(e, 1)" @dblclick="resetLeft()" />

      <!-- 中：预览 / 批量表格 -->
      <div v-if="mode === 'form'" ref="stageEl" class="stage">
        <div class="canvas-wrap" :style="{ width: W * zoom + 'px', height: H * zoom + 'px' }">
          <canvas ref="canvasEl"></canvas>
        </div>
      </div>
      <div v-else class="table-stage">
        <el-table :data="tableRows" size="small" border stripe height="100%">
          <el-table-column prop="name" label="卡名" width="150" fixed>
            <template #default="{ row }">
              <el-input v-model="row.name" size="small" @input="touch(row)" />
            </template>
          </el-table-column>
          <el-table-column
            v-for="f in tableFields" :key="f.id"
            :label="f.label || f.key" min-width="150">
            <template #default="{ row }">
              <el-input
                v-if="f.kind === 'text'" v-model="row.fields[f.key]" size="small"
                :class="{ dirty: isDirty(row, f.key) }" @input="touch(row)" />
              <el-input
                v-else-if="isMultiline(f)" v-model="row.fields[f.key]" size="small"
                type="textarea" :rows="2" @input="touch(row)" />
              <el-input-number
                v-else-if="f.kind === 'number'" v-model="row.fields[f.key]" size="small"
                :min="f.constraint?.min ?? -Infinity" :max="f.constraint?.max ?? Infinity"
                :controls="false" style="width:100%" @change="touch(row)" />
              <el-select
                v-else-if="f.kind === 'enum'" v-model="row.fields[f.key]" size="small"
                clearable style="width:100%" @change="touch(row)">
                <el-option v-for="o in f.constraint?.options || []" :key="o" :label="o" :value="o" />
              </el-select>
              <span v-else class="muted">—</span>
            </template>
          </el-table-column>
          <el-table-column prop="tags" label="标签" width="160">
            <template #default="{ row }">
              <el-input v-model="row.tagText" size="small" placeholder="逗号分隔" @input="touch(row)" />
            </template>
          </el-table-column>
          <el-table-column label="预览" width="70" fixed="right">
            <template #default="{ row }">
              <el-button size="small" text @click="previewRow(row)">查看</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <!-- 拖动调宽（双击恢复默认）。表格模式下没有右侧栏，抓手也跟着隐藏 -->
      <div v-if="mode === 'form'" class="grip" title="拖动调宽 · 双击恢复默认"
           @pointerdown="(e: PointerEvent) => dragRight(e, -1)" @dblclick="resetRight()" />

      <!-- 右：表单 -->
      <aside v-if="mode === 'form'" class="side right" :style="{ width: rightW + 'px' }">
        <div v-if="!card" class="empty" style="padding:24px 8px">选择或新建一张卡牌</div>
        <template v-else>
          <div class="side-title">卡牌</div>
          <el-form label-width="76px" size="small" style="padding: 0 12px">
            <el-form-item label="卡名">
              <el-input v-model="card.name" @change="mark" />
            </el-form-item>
            <el-form-item label="标签">
              <el-input v-model="tagText" placeholder="逗号分隔" @change="applyTags" />
            </el-form-item>
            <el-divider content-position="left">字段</el-divider>

            <!-- 孤卡：模板被删了。给「改挂模板」与「删卡」两条出路 -->
            <div v-if="tplMissing" class="no-fields">
              <div>
                这张卡引用的模板已不存在（可能被删除），所以没有可填字段。
                给它换一个模板，或者直接删掉这张卡：
              </div>
              <div class="row" style="gap: 6px; margin-top: 8px; flex-wrap: wrap">
                <el-select v-model="newTplId" size="small" style="width: 170px"
                           placeholder="选择模板">
                  <el-option v-for="t in templates" :key="t.id" :label="t.name" :value="t.id" />
                </el-select>
                <el-button size="small" type="primary" :disabled="!newTplId"
                           @click="repointTemplate">改挂到这个模板</el-button>
                <el-button size="small" type="danger" text @click="delCard">删除这张卡</el-button>
              </div>
            </div>

            <!-- 模板没配字段时明确说清楚，别让用户对着空白面板发懵 -->
            <div v-else-if="!editableFields.length && !fixedFields.length" class="no-fields">
              这张卡使用的模板「{{ tpl?.name }}」还没有配置任何字段，
              所以没有可填内容。<br />
              请先去
              <el-button link type="primary" size="small" @click="editTemplate">
                模板编辑器
              </el-button>
              添加字段，或回项目页换一个模板新建卡牌。
            </div>

            <template v-for="f in editableFields" :key="f.id">
              <el-form-item :label="f.label || f.key">
                <el-input
                  v-if="f.kind === 'text'"
                  v-model="card.fields[f.key]" @change="mark" />
                <el-input
                  v-else-if="isMultiline(f)"
                  v-model="card.fields[f.key]" type="textarea" :rows="4" @change="mark" />
                <el-input-number
                  v-else-if="f.kind === 'number'"
                  v-model="card.fields[f.key]"
                  :min="f.constraint?.min ?? -Infinity"
                  :max="f.constraint?.max ?? Infinity" @change="mark" />
                <el-select
                  v-else-if="f.kind === 'enum'"
                  v-model="card.fields[f.key]" clearable @change="mark">
                  <el-option v-for="o in f.constraint?.options || []" :key="o" :label="o" :value="o" />
                </el-select>
                <div v-else-if="f.kind === 'image'" class="img-field">
                  <img v-if="card.fields[f.key]" :src="resolveAsset(card.fields[f.key])" />
                  <div v-else class="ph">未设置</div>
                  <div class="row" style="gap:6px; flex-wrap: wrap">
                    <el-button size="small" @click="pickImage(f)">本地上传</el-button>
                    <el-button size="small" @click="openLibrary(f)">从资源库选择</el-button>
                    <el-button size="small" type="primary" plain @click="openAi(f)">AI 生成</el-button>
                    <el-button v-if="card.fields[f.key]" size="small" text @click="clearImage(f)">清除</el-button>
                  </div>
                </div>
                <div v-else-if="f.kind === 'icon'" class="img-field">
                  <img v-if="card.fields[f.key]" :src="resolveAsset(card.fields[f.key])" />
                  <div v-else class="ph">未设置</div>
                  <el-button size="small" @click="showIconPicker(f)">选择图标</el-button>
                </div>
              </el-form-item>
            </template>
            <el-divider content-position="left">模板固定</el-divider>
            <div v-for="f in fixedFields" :key="f.id" class="fixed-row">
              <span class="muted">{{ f.label }}</span>
              <span>{{ f.value }}</span>
            </div>
          </el-form>
          <div style="padding: 0 12px">
            <el-button type="danger" text size="small" @click="delCard">删除这张卡</el-button>
          </div>
        </template>
      </aside>
    </div>

    <input ref="fileEl" type="file" accept="image/*" hidden @change="onFile" />

    <!-- 图标选择 -->
    <el-dialog v-model="showIcons" title="选择图标" width="640">
      <el-select v-model="iconLib" size="small" style="width:140px">
        <el-option v-for="l in libs" :key="l.id" :label="l.name" :value="l.id" />
      </el-select>
      <div class="icon-grid">
        <div v-for="a in icons" :key="a.id" class="icon-cell" @click="chooseIcon(a)">
          <img :src="resolveAsset(a.id)" />
          <span>{{ a.name }}</span>
        </div>
      </div>
    </el-dialog>

    <!-- 新建卡牌：与项目页共用同一个对话框（先选模板） -->
    <NewCardDialog v-model="showNewCard" :pid="pid" :templates="templates"
                   :default-template-id="card?.templateId" @created="onCardCreated" />

    <!-- 批量导入（字段映射 + 校验预览） -->
    <MappingDialog
      v-model="showImport" :pid="pid" :templates="templates"
      :default-tpl="curTplId" @done="afterImport" />

    <!-- §P5-E1 单张导出 -->
    <ExportDialog v-model="showExport" :pid="pid" :card-id="card?.id" :templates="templates" />

    <!-- AI 生成配图：提交后转后台，完成后弹通知引导到「从资源库选择」 -->
    <AiGenerateDialog
      v-model="showAi" :pid="pid" kind="cardart"
      :template-id="card?.templateId" :card-id="card?.id" :field-key="aiField?.key || ''"
      :label="card?.name" />

    <!-- 从资源库选图片（AI 刚生成的排在最前） -->
    <AssetPickerDialog v-model="showLib2" type="image" @picked="onLibArt" />

    <!-- 本地图片先裁到该字段的比例再上传 -->
    <ImageCropDialog v-model="showCrop" :file="cropFile" :aspect="cropAspect"
                     :aspect-text="cropAspectText" @cropped="onCropped" />
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import ExportDialog from '../components/ExportDialog.vue'
import NewCardDialog from '../components/NewCardDialog.vue'
import AiGenerateDialog from '../components/AiGenerateDialog.vue'
import AssetPickerDialog from '../components/AssetPickerDialog.vue'
import ImageCropDialog from '../components/ImageCropDialog.vue'
import { useRoute, useRouter } from 'vue-router'
import { Canvas } from 'fabric'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api, resolveAsset } from '../api/client'
import { renderTemplate } from '../render/templateRenderer'
import { useUnsavedGuard } from '../composables/useUnsavedGuard'
import { useWheelZoom } from '../composables/useWheelZoom'
import { usePanelResize } from '../composables/usePanelResize'
import MappingDialog from '../components/MappingDialog.vue'

const route = useRoute()
const router = useRouter()
const pid = computed(() => route.params.pid as string)
const cid = computed(() => route.params.cid as string | undefined)

const loading = ref(false)
const dirty = ref(false)
const zoom = ref(0.55)

// 左右侧栏宽度可拖拽调节，值记在 localStorage（双击抓手恢复默认）
const { width: leftW, onDown: dragLeft, reset: resetLeft } = usePanelResize('cardLeft', 250)
const { width: rightW, onDown: dragRight, reset: resetRight } = usePanelResize('cardRight', 360)
const mode = ref<'form' | 'table'>('form')
const list = ref<any[]>([])
const q = ref('')
const templates = ref<any[]>([])
const tpl = ref<any>(null)
const card = ref<any>(null)
/** 卡牌引用的模板已不存在（孤卡） */
const tplMissing = ref(false)
const newTplId = ref('')
const tagText = ref('')
const canvasEl = ref<HTMLCanvasElement>()
const stageEl = ref<HTMLElement>()
const fileEl = ref<HTMLInputElement>()
let canvas: Canvas | null = null
let pickTarget: any = null

const W = computed(() => tpl.value?.canvas?.w ?? 745)
const H = computed(() => tpl.value?.canvas?.h ?? 1040)
const editableFields = computed(() =>
  (tpl.value?.fields ?? []).filter((f: any) => f.binding !== 'fixed'))

/** 字段是否要多行输入框：`multiline` 显式指定，缺省沿用历史别名 textarea */
function isMultiline(f: any) {
  return f.multiline === undefined || f.multiline === null ? f.kind === 'textarea' : !!f.multiline
}
const fixedFields = computed(() =>
  (tpl.value?.fields ?? []).filter((f: any) => f.binding === 'fixed'))
const curTplId = computed(() => tpl.value?.id || templates.value[0]?.id || '')

// 图标选择
const showIcons = ref(false)
const libs = ref<any[]>([])
const iconLib = ref('elements')
const icons = ref<any[]>([])
const showImport = ref(false)
const showExport = ref(false)

// ---- 表格批量模式 ---------------------------------------------------------
const tableTplId = ref('')
const tableQ = ref('')
const tableRows = ref<any[]>([])
const edited = ref<Record<string, any>>({})
const editCount = computed(() => Object.keys(edited.value).length)
const tableFields = computed(() => {
  const t = templates.value.find((x: any) => x.id === tableTplId.value)
  return (t?.fields ?? []).filter((f: any) => f.binding !== 'fixed')
})

async function loadTable() {
  const p = new URLSearchParams()
  if (tableTplId.value) p.set('templateId', tableTplId.value)
  if (tableQ.value) p.set('q', tableQ.value)
  p.set('full', '1')  // 轻量索引不含 fields，表格编辑必须取完整卡牌
  const cards = await api.get(`/projects/${pid.value}/cards?${p}`)
  const t = templates.value.find((x: any) => x.id === tableTplId.value)
  const keys = (t?.fields ?? []).map((f: any) => f.key)
  tableRows.value = cards.map((c: any) => ({
    id: c.id,
    name: c.name,
    fields: keys.reduce((o: any, k: string) => {
      o[k] = c.fields?.[k] ?? ''
      return o
    }, {}),
    tagText: (c.tags || []).join(',')
  }))
  edited.value = {}
}

function touch(row: any) {
  edited.value = { ...edited.value, [row.id]: true }
}

function isDirty(row: any, key: string) {
  return !!edited.value[row.id]
}

async function saveTable() {
  const ids = Object.keys(edited.value)
  if (!ids.length) return
  const payload = tableRows.value
    .filter((r) => ids.includes(r.id))
    .map((r) => ({
      id: r.id,
      name: r.name,
      tags: r.tagText.split(/[,，]/).map((s: string) => s.trim()).filter(Boolean),
      fields: r.fields
    }))
  const r = await api.post(`/projects/${pid.value}/cards/bulk-update`, { cards: payload })
  ElMessage.success(`已保存 ${r.updated} 张卡`)
  edited.value = {}
  await loadList()
  await loadTable()
}

function previewRow(row: any) {
  mode.value = 'form'
  open(row.id)
}

async function onModeChange(v: any) {
  if (v === 'table') {
    // 离开表单模式：canvas 元素会被 v-if 销毁，必须先释放 Fabric 实例
    disposeCanvas()
    if (!tableTplId.value) tableTplId.value = curTplId.value
    await loadTable()
    return
  }
  // 回到表单模式：<canvas> 是新建的 DOM 元素，Fabric 画布必须重新绑定并重绘，
  // 否则旧的 Canvas 实例还指向已经被移除的元素 → 显示白卡
  await nextTick()
  if (card.value) { ensureCanvas(); redraw() }
  else if (list.value[0]) await open(list.value[0].id)
}

// ---- 数据导出（§P5-E3 纯数据） -------------------------------------------
async function exportData(fmt: string) {
  const tid = mode.value === 'table' ? tableTplId.value : curTplId.value
  const url = `/api/projects/${pid.value}/cards/export?format=${fmt}` +
    (tid ? `&templateId=${tid}` : '')
  if (fmt === 'csv') {
    window.open(url, '_blank')
    return
  }
  const data = await api.get(url)
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = 'cards.json'
  a.click()
  URL.revokeObjectURL(a.href)
}

function tplName(id: string) {
  return templates.value.find((t: any) => t.id === id)?.name || ''
}

async function loadList() {
  const p = new URLSearchParams()
  if (q.value) p.set('q', q.value)
  list.value = await api.get(`/projects/${pid.value}/cards?${p}`)
}

async function loadTemplates() {
  templates.value = await api.get(`/projects/${pid.value}/templates`)
  if (!tableTplId.value && templates.value[0]) tableTplId.value = templates.value[0].id
}

async function open(id: string) {
  loading.value = true
  try {
    card.value = await api.get(`/cards/${id}?pid=${pid.value}`)
    tplMissing.value = false
    try {
      tpl.value = await api.get(`/templates/${card.value.templateId}?pid=${pid.value}`)
    } catch {
      // 孤卡：模板被删了，卡还活着但没有字段可填。以前这里会抛异常直接把
      // open() 打断（页面停在一半状态、右栏空白），现在给用户一个出口。
      tpl.value = null
      tplMissing.value = true
      newTplId.value = templates.value[0]?.id || ''
    }
    tagText.value = (card.value.tags || []).join(',')
    router.replace(`/project/${pid.value}/cards/${id}`)
    await nextTick()
    if (mode.value === 'form') { ensureCanvas(); redraw() }
    dirty.value = false
  } finally { loading.value = false }
}

function disposeCanvas() {
  if (canvas) { canvas.dispose(); canvas = null }
}

function ensureCanvas() {
  disposeCanvas()
  if (!canvasEl.value) return
  canvas = new Canvas(canvasEl.value, {
    width: W.value * zoom.value, height: H.value * zoom.value, backgroundColor: '#fff'
  })
  canvas.setZoom(zoom.value)
}

let raf = 0
async function redraw() {
  if (!canvas) return
  cancelAnimationFrame(raf)
  raf = requestAnimationFrame(async () => {
    try {
      await renderTemplate(canvas!, tpl.value, { card: card.value, interactive: false })
    } catch (err: any) {
      // rAF 回调里的异常没人接 → 只会看到"画布一片白"，所以自己兜住并说出来
      console.error('[renderTemplate]', err)
      ElMessage.error('画布渲染失败：' + (err?.message || err))
    }
  })
}
function mark() { dirty.value = true; redraw() }

function applyTags() {
  card.value.tags = tagText.value.split(/[,，]/).map((s: string) => s.trim()).filter(Boolean)
  dirty.value = true
}

async function save() {
  await api.put(`/cards/${card.value.id}`, { ...card.value, projectId: pid.value })
  dirty.value = false
  ElMessage.success('已保存')
  await loadList()
}

// 有未保存改动时保护离开（切到另一张卡也走这个守卫 —— 路由参数变化同样触发）
useUnsavedGuard(() => dirty.value && !!card.value?.id, save)

/**
 * 新建卡牌：走和项目页一样的对话框（先选模板）。
 * 以前这里直接用 `curTplId`（当前卡的模板，兜底 `templates[0]`）闷头建卡 ——
 * 兜底那个可能是刚建的空模板，建出来右栏一片空白，用户以为是 bug。
 * 默认值取「当前卡的模板」最顺手（多半想再建一张同类卡），改不改由用户决定。
 */
const showNewCard = ref(false)

function openNewCard() {
  if (!templates.value.length) return ElMessage.warning('请先创建模板')
  showNewCard.value = true
}

async function onCardCreated(c: any) {
  await loadList()
  mode.value = 'form'
  await open(c.id)
}

async function delCard() {
  await ElMessageBox.confirm(`删除「${card.value.name}」？`, '提示', { type: 'warning' })
  await api.del(`/cards/${card.value.id}?pid=${pid.value}`)
  card.value = null
  dirty.value = false          // 卡没了，未保存标记也要清掉，否则离开时白弹一次确认
  tplMissing.value = false
  canvas?.clear()
  await loadList()
}

// ---- 图片 / 图标 ----
function pickImage(f: any) { pickTarget = f; fileEl.value?.click() }

const cropFile = ref<File | null>(null)
const showCrop = ref(false)
const cropAspect = ref(0)
const cropAspectText = ref('')

async function onFile(e: Event) {
  const el = e.target as HTMLInputElement
  const file = el.files?.[0]
  el.value = ''                       // 立刻清空，同一个文件再选一次也能触发
  if (!file || !pickTarget) return
  // 按该图片区域的比例裁：区域是 640×430 就别塞张 1:1 进去（会被 cover 切掉一半）
  const r = pickTarget.rect || []
  cropAspect.value = r[2] && r[3] ? r[2] / r[3] : 0
  cropAspectText.value = cropAspect.value ? `区域 ${r[2]}×${r[3]}` : ''
  cropFile.value = file
  showCrop.value = true
}

async function onCropped(blob: Blob) {
  if (!pickTarget) return
  const form = new FormData()
  form.append('file', new File([blob], `${pickTarget.key || 'image'}.png`,
                              { type: 'image/png' }))
  form.append('type', 'image')
  const a = await api.upload('/assets/upload', form)
  card.value.fields[pickTarget.key] = a.id
  mark()
  ElMessage.success('已裁切并套用到该字段')
}

function clearImage(f: any) { card.value.fields[f.key] = null; mark() }

/** 跳到当前模板的编辑器（卡牌页发现模板没字段时的出口） */
function editTemplate() {
  if (card.value?.templateId) {
    router.push(`/project/${pid.value}/template/${card.value.templateId}`)
  }
}

/** 孤卡改挂到别的模板：原有字段值保留，新模板里同名的 key 会直接显示出来 */
async function repointTemplate() {
  const t = templates.value.find((x: any) => x.id === newTplId.value)
  if (!t || !card.value) return
  try {
    await ElMessageBox.confirm(
      `把「${card.value.name}」改挂到模板「${t.name}」？\n` +
      '原有字段值会保留，但只有新模板里存在同名字段的内容才会显示与导出。',
      '切换模板', { type: 'warning', confirmButtonText: '改挂' })
  } catch { return }
  await api.put(`/cards/${card.value.id}`,
                { ...card.value, projectId: pid.value, templateId: t.id })
  await open(card.value.id)
  ElMessage.success('已切换模板')
}

// ---- AI 生成配图 / 从资源库选图 --------------------------------------------
const showAi = ref(false)
const showLib2 = ref(false)
const aiField = ref<any>(null)

function openAi(f: any) {
  aiField.value = f
  showAi.value = true
}

function openLibrary(f: any) {
  aiField.value = f
  showLib2.value = true
}

/** 应用一张图到当前字段（AI 生成的结果也是走这里，从资源库挑） */
function onLibArt(assetId: string) {
  if (aiField.value) {
    card.value.fields[aiField.value.key] = assetId
    mark()          // 标脏，让「保存」按钮亮起来
  }
}

async function showIconPicker(f: any) {
  pickTarget = f
  if (!libs.value.length) libs.value = await api.get('/asset-libraries')
  iconLib.value = f.iconLibrary || libs.value[0]?.id
  await loadIcons()
  showIcons.value = true
}

async function loadIcons() {
  icons.value = await api.get(`/assets?type=icon&library=${iconLib.value}`)
}

function chooseIcon(a: any) {
  card.value.fields[pickTarget.key] = a.id
  showIcons.value = false
  mark()
}

async function afterImport() {
  await loadList()
  if (mode.value === 'table') await loadTable()
}

watch(iconLib, loadIcons)
watch(zoom, () => {
  if (!canvas || mode.value !== 'form') return
  canvas.setDimensions({ width: W.value * zoom.value, height: H.value * zoom.value })
  canvas.setZoom(zoom.value); canvas.requestRenderAll()
})

/** 适应窗口宽度（与模板编辑器同款算法） */
function fitZoom() {
  if (!stageEl.value) return
  const avail = stageEl.value.clientWidth - 40
  zoom.value = Math.max(0.15, Math.min(1.5, avail / W.value))
}

// 滚轮 / 触摸板缩放：Ctrl(⌘)+滚轮始终缩放；普通滚轮只在画布滚不动时用来缩放
useWheelZoom({ stage: stageEl, zoom, min: 0.15, max: 3 })
watch(() => route.params.cid, async (v) => { if (v) await open(v as string) })

onMounted(async () => {
  await loadTemplates()
  await loadList()
  if (cid.value) await open(cid.value)
  else if (list.value[0]) await open(list.value[0].id)
})
onUnmounted(() => { canvas?.dispose(); canvas = null })
</script>

<style scoped>
.editor { display: flex; flex-direction: column; height: 100%; }
.toolbar {
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap; flex: none;
  padding: 8px 14px; background: var(--panel); border-bottom: 1px solid var(--border);
}
.spacer { flex: 1; }
.body { flex: 1; display: flex; min-height: 0; }
/* 侧栏抓手：6px 热区，平时隐形，悬停给个提示色（宽度由内联样式控制） */
.grip {
  flex: none; width: 6px; cursor: col-resize; position: relative; z-index: 3;
  background: transparent; transition: background .12s;
}
.grip:hover { background: var(--accent-soft); }
.side { width: 240px; flex: none; background: var(--panel); border-right: 1px solid var(--border); overflow: hidden; }
.side.right { width: 320px; border-right: none; border-left: 1px solid var(--border); padding: 12px 0; overflow: auto; }
.side-title { font-size: 12px; font-weight: 700; color: var(--muted); padding: 4px 12px 6px; }
.item { padding: 8px 12px; cursor: pointer; border-bottom: 1px solid var(--row-line); }
.item:hover { background: var(--panel-soft); }
.item.active { background: var(--accent-soft); font-weight: 600; }
.cname { display: block; font-size: 13px; }
.stage { flex: 1; overflow: auto; background: var(--stage); padding: 20px; display: flex; justify-content: center; }
.canvas-wrap { background: var(--card); box-shadow: var(--shadow-card); align-self: flex-start; }
.table-stage { flex: 1; min-width: 0; padding: 10px; overflow: hidden; }
.dirty :deep(.el-input__wrapper) { box-shadow: 0 0 0 1px var(--accent) inset; }
.no-fields {
  font-size: 12px; line-height: 1.8; color: var(--warn-text); background: var(--warn-bg);
  border: 1px solid var(--warn-border); border-radius: 6px; padding: 10px; margin-bottom: 10px;
}
.img-field { width: 100%; }
.img-field img { width: 100%; max-height: 90px; object-fit: contain; background: var(--panel-soft); }
.img-field .ph { color: var(--muted); font-size: 12px; padding: 6px 0; }
.fixed-row { display: flex; justify-content: space-between; font-size: 12px; padding: 3px 12px; }
.icon-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(72px, 1fr)); gap: 8px; margin-top: 10px; }
.icon-cell { text-align: center; cursor: pointer; padding: 6px; border-radius: 6px; }
.icon-cell:hover { background: var(--panel-soft); }
.icon-cell img { width: 34px; height: 34px; color: var(--text); }
.icon-cell span { display: block; font-size: 11px; color: var(--muted); margin-top: 2px; }
.muted { color: var(--muted); }
</style>
