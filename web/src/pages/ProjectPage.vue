<template>
  <div class="page" v-loading="loading">
    <div class="row" style="margin-bottom: 14px">
      <div>
        <h1 class="page-title">{{ project?.name }}</h1>
        <div class="page-sub">
          {{ project?.description || '暂无描述' }}
          · {{ stats.cardCount }} 张卡牌 · {{ stats.templateCount }} 个模板
        </div>
      </div>
      <div class="spacer" />
      <!-- §P5-E3 项目包 -->
      <el-button @click="exportPackage">导出项目包</el-button>
      <el-button @click="pkgEl?.click()">导入项目包</el-button>
      <el-button @click="refresh">刷新</el-button>
      <el-button @click="router.push('/')">返回首页</el-button>
    </div>

    <el-tabs v-model="tab">
      <!-- 概览 -->
      <el-tab-pane label="概览" name="overview">
        <div class="ov-grid">
          <!-- 左栏：项目设定（创作简报，§4.4 / §6.11）—— 常驻直接可见，点「编辑」原地改 -->
          <aside class="ov-side">
            <ProjectBriefPanel :pid="pid" :brief="project?.brief" @saved="onBriefSaved" />
          </aside>

          <!-- 右栏：数值与内容 -->
          <section class="ov-main">
            <div class="stat-row">
              <div class="panel stat-box">
                <div class="num">{{ stats.cardCount }}</div>
                <div class="lbl">卡牌总数</div>
              </div>
              <div class="panel stat-box">
                <div class="num">{{ stats.templateCount }}</div>
                <div class="lbl">模板数</div>
              </div>
              <div class="panel stat-box">
                <div class="num">{{ fieldTotal }}</div>
                <div class="lbl">字段总数</div>
              </div>
              <div class="panel stat-box">
                <div class="num">{{ stats.distributions?.length || 0 }}</div>
                <div class="lbl">数值字段</div>
              </div>
            </div>

            <h3 class="sec">模板</h3>
            <div v-if="!stats.templates?.length" class="empty">还没有模板</div>
            <div v-else class="card-grid">
              <div v-for="t in stats.templates" :key="t.id" class="panel tpl-card">
                <div class="tpl-name">{{ t.name }}</div>
                <div class="muted" style="font-size: 12px; margin: 6px 0">
                  {{ t.canvas?.w }}×{{ t.canvas?.h }}px · {{ t.fieldCount }} 字段 · {{ t.cardCount }} 张卡
                </div>
                <div class="row">
                  <el-button size="small" @click="editTemplate(t.id)">编辑</el-button>
                  <el-button size="small" @click="openCardDialog(t.id)">新建卡牌</el-button>
                </div>
              </div>
            </div>

            <h3 class="sec">数值分布</h3>
            <div v-if="!stats.distributions?.length" class="empty">
              还没有可统计的数值字段（模板里需要有 number / enum 类型的字段）
            </div>
            <div v-else class="chart-grid">
              <div v-for="d in stats.distributions" :key="d.templateId + d.key" class="panel">
                <div class="chart-title">{{ d.templateName }} · {{ d.label }}</div>
                <div :ref="el => setChart(el, d)" class="chart"></div>
                <div v-if="outliers[d.templateId + d.key]?.length" class="outlier">
                  <el-tag type="warning" size="small">离群 {{ outliers[d.templateId + d.key].length }} 项</el-tag>
                  <span class="muted" style="font-size: 12px; margin-left: 6px">
                    {{ outliers[d.templateId + d.key].slice(0, 8).join('、') }}
                  </span>
                </div>
              </div>
            </div>
          </section>
        </div>
      </el-tab-pane>

      <!-- 卡牌 -->
      <el-tab-pane :label="`卡牌 (${cards.length})`" name="cards">
        <div class="row" style="margin-bottom: 12px">
          <el-input v-model="q" placeholder="搜索卡名" clearable style="width: 200px" />
          <el-select v-model="filterTemplate" placeholder="全部模板" clearable style="width: 180px">
            <el-option v-for="t in stats.templates" :key="t.id" :label="t.name" :value="t.id" />
          </el-select>
          <el-button :type="selected.length ? 'warning' : 'default'"
                     @click="selected.length ? selected = [] : selectAll()">
            {{ selected.length ? `取消勾选 ${selected.length}` : '批量勾选' }}
          </el-button>
          <el-button v-if="selected.length" type="danger" plain @click="delSelected">
            删除选中 {{ selected.length }}
          </el-button>
          <div class="spacer" />
          <!-- §P5-E2 -->
          <el-button :disabled="!cards.length" @click="showExport = true">导出卡牌</el-button>
          <!-- §P5-E3 纯数据 -->
          <el-dropdown size="default" @command="exportData">
            <el-button>数据导出 ▾</el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="csv">卡牌数据 CSV</el-dropdown-item>
                <el-dropdown-item command="json">卡牌数据 JSON</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <el-button type="primary" :disabled="!stats.templates?.length"
                     @click="openCardDialog()">
            新建卡牌
          </el-button>
        </div>
        <div v-if="!cards.length" class="empty">没有匹配的卡牌</div>
        <div v-else class="card-grid">
          <div v-for="c in cards" :key="c.id" class="panel mini-card"
               :class="{ picked: selected.includes(c.id) }" @click="openCard(c.id)">
            <el-checkbox :model-value="selected.includes(c.id)"
                         class="pick" @click.stop
                         @change="togglePick(c.id)" />
            <div class="mini-name">{{ c.name }}</div>
            <div class="muted" style="font-size: 12px">{{ tplName(c.templateId) }}</div>
            <div v-if="c.tags?.length" class="tags">
              <el-tag v-for="t in c.tags" :key="t" size="small" effect="plain">{{ t }}</el-tag>
            </div>
          </div>
        </div>
      </el-tab-pane>

      <!-- 模板 -->
      <el-tab-pane :label="`模板 (${stats.templateCount})`" name="templates">
        <div class="row" style="margin-bottom: 12px">
          <div class="spacer" />
          <el-button type="primary" @click="openTplDialog">新建模板</el-button>
        </div>
        <div v-if="!stats.templates?.length" class="empty">还没有模板</div>
        <div v-else class="card-grid">
          <div v-for="t in stats.templates" :key="t.id" class="panel tpl-card">
            <div class="tpl-name">{{ t.name }}</div>
            <div class="muted" style="font-size: 12px; margin: 6px 0">
              {{ t.canvas?.w }}×{{ t.canvas?.h }}px · {{ t.fieldCount }} 字段
            </div>
            <div class="row">
              <el-button size="small" @click="editTemplate(t.id)">编辑</el-button>
              <el-button size="small" @click="dupTemplate(t)">复制</el-button>
              <el-button size="small" type="danger" text @click="delTemplate(t)">删除</el-button>
            </div>
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>

    <input ref="pkgEl" type="file" accept=".zip" hidden @change="onPackageFile" />

    <!-- §P5-E2 批量导出（全部 / 当前筛选 / 已勾选，在弹窗里选） -->
    <ExportDialog v-model="showExport" :pid="pid" :card-ids="exportIds" :templates="templates" />

    <!-- 新建卡牌：先选模板（默认挑字段最多的，避免挂到空模板上）。与卡牌页共用组件 -->
    <NewCardDialog v-model="showCard" :pid="pid" :templates="stats.templates || []"
                   :default-template-id="newCardTplId" @created="onCardCreated" />

    <!-- 新建模板：选常见卡牌尺寸（物理尺寸优先，像素按 DPI 换算） -->
    <el-dialog v-model="showTpl" title="新建模板" width="560">
      <el-form label-width="92px">
        <el-form-item label="模板名称">
          <el-input v-model="tplForm.name" placeholder="例如：法术卡" />
        </el-form-item>
        <el-form-item label="卡牌尺寸">
          <el-select v-model="tplForm.sizeId" style="width: 100%">
            <el-option v-for="s in CARD_SIZES" :key="s.id" :label="s.name" :value="s.id">
              <span>{{ s.name }}</span>
              <span class="opt-hint">{{ s.hint }}</span>
            </el-option>
          </el-select>
        </el-form-item>
        <el-form-item v-if="tplForm.sizeId === 'custom'" label="自定义 (mm)">
          <el-input-number v-model="tplForm.w_mm" :min="20" :max="500" :controls="false"
                           style="width: 90px" />
          <span style="padding: 0 6px">×</span>
          <el-input-number v-model="tplForm.h_mm" :min="20" :max="500" :controls="false"
                           style="width: 90px" />
          <span class="muted" style="margin-left: 8px">宽 × 高</span>
        </el-form-item>
        <el-form-item label="DPI">
          <el-radio-group v-model="tplForm.dpi">
            <el-radio-button :value="300">300（推荐）</el-radio-button>
            <el-radio-button :value="600">600</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="成品规格">
          <span class="muted">{{ sizePreview }}</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showTpl = false">取消</el-button>
        <el-button type="primary" @click="createTemplate">创建并编辑</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import * as echarts from 'echarts'
import { api } from '../api/client'
import ExportDialog from '../components/ExportDialog.vue'
import NewCardDialog from '../components/NewCardDialog.vue'
import ProjectBriefPanel from '../components/ProjectBriefPanel.vue'
import { BLEED_MM, CARD_SIZES, canvasSpec } from '../constants/cardSizes'
import { useTheme } from '../composables/useTheme'

const route = useRoute()
const router = useRouter()
const pid = computed(() => route.params.pid as string)

const loading = ref(false)
const tab = ref('overview')
const project = ref<any>(null)
const stats = ref<any>({ cardCount: 0, templateCount: 0, templates: [], distributions: [] })
const cards = ref<any[]>([])
const q = ref('')
const filterTemplate = ref('')

const fieldTotal = computed(() =>
  (stats.value.templates || []).reduce((s: number, t: any) => s + (t.fieldCount || 0), 0))

const outliers = computed(() => {
  const out: Record<string, any[]> = {}
  for (const d of stats.value.distributions || []) {
    const k = d.templateId + d.key
    if (d.kind === 'number') {
      const bad = d.values.filter((v: any) =>
        (d.min != null && Number(v) < d.min) || (d.max != null && Number(v) > d.max))
      if (bad.length) out[k] = bad
    } else if (d.options?.length) {
      const bad = d.values.filter((v: any) => !d.options.includes(v))
      if (bad.length) out[k] = bad
    }
  }
  return out
})

async function refresh() {
  loading.value = true
  try {
    project.value = await api.get(`/projects/${pid.value}`)
    stats.value = await api.get(`/projects/${pid.value}/stats`)
    templates.value = await api.get(`/projects/${pid.value}/templates`)
    await loadCards()
    await nextTick()
    renderCharts()
  } finally { loading.value = false }
}

async function loadCards() {
  const p = new URLSearchParams()
  if (q.value) p.set('q', q.value)
  if (filterTemplate.value) p.set('templateId', filterTemplate.value)
  cards.value = await api.get(`/projects/${pid.value}/cards?${p}`)
}

function tplName(id: string) {
  return (stats.value.templates || []).find((t: any) => t.id === id)?.name || '—'
}

// 导出/复制需要的完整模板对象（stats.templates 只有摘要）
const templates = ref<any[]>([])

// ---- 项目设定（创作简报，§4.4）：左栏 ProjectBriefPanel 常驻，保存后回写本地 ----
function onBriefSaved(b: any) {
  if (project.value) project.value.brief = b
}

// ---- 图表 ---------------------------------------------------------------
const { isDark } = useTheme()
const chartEls: Record<string, HTMLElement> = {}
const chartObjs: Record<string, echarts.ECharts> = {}
function setChart(el: any, d: any) {
  const k = d.templateId + d.key
  if (el) chartEls[k] = el
}

/** 图表不跟 Element Plus 的暗色变量走，配色从 CSS 变量现读，切主题时重绘 */
function chartTheme() {
  const cs = getComputedStyle(document.documentElement)
  const v = (n: string, fb: string) => cs.getPropertyValue(n).trim() || fb
  return {
    text: v('--chart-text', '#6b7280'),
    line: v('--chart-line', '#e3e6eb'),
    bar: v('--accent', '#8b5a2b'),
    panel: v('--panel', '#ffffff'),
    border: v('--border', '#e3e6eb')
  }
}

function renderCharts() {
  for (const k in chartObjs) { chartObjs[k].dispose(); delete chartObjs[k] }
  const t = chartTheme()
  const tip = {
    backgroundColor: t.panel, borderColor: t.border,
    textStyle: { color: t.text }, extraCssText: 'box-shadow: var(--shadow-card)'
  }
  for (const d of stats.value.distributions || []) {
    const k = d.templateId + d.key
    const el = chartEls[k]
    if (!el) continue
    if (d.kind === 'number') {
      const buckets: Record<number, number> = {}
      for (const v of d.values) {
        const n = Number(v)
        if (Number.isNaN(n)) continue
        buckets[n] = (buckets[n] || 0) + 1
      }
      const keys = Object.keys(buckets).map(Number).sort((a, b) => a - b)
      const chart = echarts.init(el)
      chart.setOption({
        textStyle: { color: t.text },
        grid: { left: 34, right: 12, top: 16, bottom: 26 },
        xAxis: {
          type: 'category', data: keys, name: d.label,
          nameTextStyle: { color: t.text },
          axisLabel: { color: t.text },
          axisLine: { lineStyle: { color: t.line } }
        },
        yAxis: {
          type: 'value', minInterval: 1,
          axisLabel: { color: t.text },
          splitLine: { lineStyle: { color: t.line } }
        },
        series: [{
          type: 'bar', data: keys.map(x => buckets[x]), barMaxWidth: 26,
          itemStyle: { color: t.bar, borderRadius: [3, 3, 0, 0] }
        }],
        tooltip: { ...tip, trigger: 'axis' }
      })
      chartObjs[k] = chart
    } else {
      const counts: Record<string, number> = {}
      for (const v of d.values) counts[String(v)] = (counts[String(v)] || 0) + 1
      const chart = echarts.init(el)
      chart.setOption({
        textStyle: { color: t.text },
        series: [{
          type: 'pie', radius: ['40%', '68%'],
          data: Object.entries(counts).map(([name, value]) => ({ name, value })),
          label: { fontSize: 11, color: t.text }
        }],
        tooltip: { ...tip, trigger: 'item' }
      })
      chartObjs[k] = chart
    }
  }
}

// 切换亮/暗后重绘（ECharts 不认 CSS 变量，必须重新 setOption）
watch(isDark, () => setTimeout(renderCharts, 0))

// ---- 操作 ---------------------------------------------------------------
// ---- §P5-E2 批量导出（范围：全部 / 当前筛选 / 已勾选） ---------------------
const selected = ref<string[]>([])
const showExport = ref(false)
const pkgEl = ref<HTMLInputElement>()
const exportIds = computed(() =>
  selected.value.length ? selected.value : cards.value.map((c: any) => c.id))

function togglePick(id: string) {
  const i = selected.value.indexOf(id)
  if (i >= 0) selected.value.splice(i, 1)
  else selected.value.push(id)
}
function selectAll() { selected.value = cards.value.map((c: any) => c.id) }

/** 删除勾选的卡牌。一次请求搞定（后端 bulk-delete），删前必须确认。 */
async function delSelected() {
  const n = selected.value.length
  if (!n) return
  const names = cards.value.filter((c: any) => selected.value.includes(c.id))
    .slice(0, 5).map((c: any) => c.name)
  try {
    await ElMessageBox.confirm(
      `确定删除选中的 ${n} 张卡牌？${names.length ? `（${names.join('、')}${n > 5 ? ' 等' : ''}）` : ''}\n此操作不可撤销。`,
      '删除卡牌', { type: 'warning', confirmButtonText: '删除', confirmButtonClass: 'el-button--danger' })
  } catch { return }        // 用户取消
  const r = await api.post(`/projects/${pid.value}/cards/bulk-delete`,
                           { ids: selected.value })
  selected.value = []
  await refresh()
  ElMessage.success(`已删除 ${r?.deleted ?? n} 张卡牌`)
}

// ---- §P5-E3 纯数据 + 项目包 -----------------------------------------------
async function exportData(fmt: string) {
  window.open(`/api/projects/${pid.value}/cards/export?format=${fmt}`, '_blank')
}

async function exportPackage() {
  window.open(`/api/projects/${pid.value}/export/package`, '_blank')
  ElMessage.success('项目包正在导出')
}

async function onPackageFile(e: Event) {
  const f = (e.target as HTMLInputElement).files?.[0]
  if (!f) return
  const form = new FormData()
  form.append('file', f)
  try {
    const r = await api.post('/projects/import-package', form)
    ElMessage.success(
      `已导入「${r.name}」：${r.cardCount} 张卡 / ${r.templateCount} 个模板` +
      (r.missingAssets?.length ? `（缺失资源 ${r.missingAssets.length} 个）` : '')
    )
    router.push(`/project/${r.id}`)
    refresh()
  } catch (err: any) {
    ElMessage.error(err?.message || '导入失败')
  } finally {
    if (pkgEl.value) pkgEl.value.value = ''
  }
}

function openCard(cid: string) { router.push(`/project/${pid.value}/cards/${cid}`) }
function editTemplate(tid: string) { router.push(`/project/${pid.value}/template/${tid}`) }

// ---- 新建卡牌：先选模板（组件见 components/NewCardDialog.vue） -------------
const showCard = ref(false)
const newCardTplId = ref('')

/** 打开新建卡牌对话框；tid 用于「从某个模板卡片上直接新建」 */
function openCardDialog(tid?: string) {
  if (!(stats.value.templates || []).length) return ElMessage.warning('请先创建模板')
  newCardTplId.value = tid || ''
  showCard.value = true
}

function onCardCreated(c: any) { router.push(`/project/${pid.value}/cards/${c.id}`) }

// ---- 新建模板：先选卡牌尺寸（物理尺寸优先） -------------------------------
const showTpl = ref(false)
const tplForm = ref({ name: '', sizeId: 'poker', w_mm: 63, h_mm: 88, dpi: 300 })

const pickedSize = computed(() => {
  const s = CARD_SIZES.find(x => x.id === tplForm.value.sizeId)
  if (!s || s.id === 'custom') return { w_mm: tplForm.value.w_mm, h_mm: tplForm.value.h_mm }
  return { w_mm: s.w_mm, h_mm: s.h_mm }
})
const sizePreview = computed(() => {
  const { w_mm, h_mm } = pickedSize.value
  const c = canvasSpec(w_mm, h_mm, tplForm.value.dpi)
  return `${c.w}×${c.h}px @${c.dpi}dpi　·　成品 ${w_mm}×${h_mm}mm，含出血 ` +
    `${w_mm + BLEED_MM * 2}×${h_mm + BLEED_MM * 2}mm（出血 ${c.bleed}px）`
})

function openTplDialog() {
  tplForm.value = { name: '', sizeId: 'poker', w_mm: 63, h_mm: 88, dpi: 300 }
  showTpl.value = true
}

async function createTemplate() {
  const { w_mm, h_mm } = pickedSize.value
  if (!(w_mm > 0 && h_mm > 0)) return ElMessage.warning('请填写有效的尺寸')
  const t = await api.post(`/projects/${pid.value}/templates`, {
    name: tplForm.value.name || '新模板',
    canvas: canvasSpec(w_mm, h_mm, tplForm.value.dpi)
  })
  showTpl.value = false
  router.push(`/project/${pid.value}/template/${t.id}`)
}

async function dupTemplate(t: any) {
  await api.post(`/projects/${pid.value}/templates?from_id=${t.id}`)
  ElMessage.success('已复制')
  refresh()
}

async function delTemplate(t: any) {
  await ElMessageBox.confirm(`删除模板「${t.name}」？`, '提示', { type: 'warning' })
  await api.del(`/templates/${t.id}?pid=${pid.value}`)
  ElMessage.success('已删除')
  refresh()
}

watch([q, filterTemplate], loadCards)
onMounted(refresh)
</script>

<style scoped>
/* ---- 概览两栏：左一半 = 项目设定（常驻可见可编辑），右一半 = 数值/模板/分布 ---- */
.ov-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 16px;
  align-items: start;
}
.ov-side, .ov-main { min-width: 0; }

.stat-row { display: flex; gap: 14px; flex-wrap: wrap; margin-bottom: 20px; }
.stat-box { min-width: 130px; flex: 1; text-align: center; }
.stat-box .num { font-size: 28px; font-weight: 700; color: var(--accent); }
.stat-box .lbl { font-size: 12px; color: var(--muted); margin-top: 2px; }
.sec { font-size: 15px; margin: 22px 0 12px; }
.sec:first-child { margin-top: 0; }
.chart-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 14px;
}
.chart-title { font-size: 13px; font-weight: 600; margin-bottom: 6px; }
.chart { height: 180px; width: 100%; }
.outlier { margin-top: 8px; }
.tpl-name { font-weight: 700; }
.mini-card { cursor: pointer; position: relative; }
.mini-card:hover { border-color: var(--accent); }
.mini-card.picked { border-color: var(--accent); box-shadow: 0 0 0 2px var(--accent-soft) inset; }
.mini-card .pick { position: absolute; right: 6px; top: 6px; height: auto; }
.mini-name { font-weight: 600; margin-bottom: 4px; }
.tags { display: flex; gap: 5px; flex-wrap: wrap; margin-top: 8px; }
/* 新建模板/卡牌对话框：下拉项右侧的说明 */
.opt-hint { float: right; margin-left: 14px; font-size: 11px; color: var(--muted); }
.opt-hint.warn { color: var(--warn-text); }
.warn { font-size: 12px; color: var(--warn-text); line-height: 1.6; }

/* 窄屏回落成单栏（左右各半在 900px 以下太挤） */
@media (max-width: 900px) {
  .ov-grid { grid-template-columns: minmax(0, 1fr); }
}
</style>
