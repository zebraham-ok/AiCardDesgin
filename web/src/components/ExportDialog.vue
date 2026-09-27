<template>
  <el-dialog
    v-model="visible" :title="singleMode ? '导出这张卡（E1）' : '导出卡牌（E2）'"
    width="620px" :close-on-click-modal="!busy" :close-on-press-escape="!busy">
    <el-form label-width="96px" size="small">
      <!-- 范围 -->
      <!-- radio-group 根元素是 div，<label for> 指向它会触发 Chrome 的
           "Incorrect use of <label for=FORM_ELEMENT>" 警告；:for="''" 让它渲染成 div -->
      <el-form-item label="范围" v-if="!singleMode" :for="''">
        <el-radio-group v-model="scope">
          <el-radio value="all">全部卡牌（{{ allCards.length }}）</el-radio>
          <el-radio value="ids" :disabled="!idList.length">
            当前列表（{{ idList.length }}）
          </el-radio>
        </el-radio-group>
      </el-form-item>

      <el-form-item label="产物" :for="''">
        <!-- 单张模式只有「图片/单页PDF」；批量模式才有 ZIP 与拼版 PDF -->
        <el-radio-group v-model="output">
          <el-radio value="image" v-if="singleMode">图片 / 单页 PDF</el-radio>
          <el-radio value="zip" v-if="!singleMode">批量 ZIP</el-radio>
          <el-radio value="pdf" v-if="!singleMode">PDF 拼版</el-radio>
        </el-radio-group>
      </el-form-item>

      <el-form-item label="格式" v-if="singleMode" :for="''">
        <el-radio-group v-model="imgFormat">
          <el-radio value="png">PNG</el-radio>
          <el-radio value="jpg">JPG</el-radio>
          <el-radio value="pdf">PDF（单页一卡）</el-radio>
        </el-radio-group>
      </el-form-item>

      <el-form-item label="DPI" :for="''">
        <el-radio-group v-model="dpi">
          <el-radio-button v-for="d in DPI_PRESETS" :key="d" :value="d">{{ d }}</el-radio-button>
        </el-radio-group>
      </el-form-item>

      <el-form-item label="出血模式" :for="''">
        <el-radio-group v-model="bleedMode">
          <el-radio value="trim">不含出血（{{ netSize }}）</el-radio>
          <el-radio value="bleed">含出血 3mm（{{ fullSize }}）</el-radio>
        </el-radio-group>
        <div class="hint">
          不含出血用于屏幕 / TTS；送印与家用打印请用含出血
        </div>
      </el-form-item>

      <el-form-item label="出血排布" v-if="bleedMode === 'bleed' && output === 'pdf'" :for="''">
        <el-radio-group v-model="bleedShare">
          <el-radio value="shared">共享出血（省纸）</el-radio>
          <el-radio value="independent">独立出血（更好裁）</el-radio>
        </el-radio-group>
      </el-form-item>

      <el-form-item label="裁切线" v-if="bleedMode === 'bleed'">
        <el-switch v-model="cutLines" />
        <span class="hint2">画在净尺寸边界（四角角线）</span>
      </el-form-item>

      <el-form-item label="透明背景" v-if="output === 'image' && imgFormat === 'png'
        && bleedMode === 'trim'">
        <el-switch v-model="transparent" />
      </el-form-item>

      <!-- ZIP -->
      <template v-if="output === 'zip'">
        <el-form-item label="文件名">
          <el-input v-model="pattern" placeholder="{{template}}_{{name}}" />
        </el-form-item>
        <el-form-item label="数据清单">
          <el-checkbox v-model="withData">附带 cards.csv / cards.json</el-checkbox>
        </el-form-item>
        <el-form-item label="按模板分包" v-if="templates.length > 1">
          <el-switch v-model="groupByTemplate" />
        </el-form-item>
      </template>

      <!-- PDF 拼版 -->
      <template v-if="output === 'pdf' && !singleMode">
        <el-divider content-position="left">拼版</el-divider>
        <el-form-item label="纸张">
          <el-select v-model="paper" style="width: 110px">
            <el-option v-for="p in Object.keys(PAPERS)" :key="p" :label="p" :value="p" />
          </el-select>
          <el-checkbox v-model="landscape" style="margin-left: 8px">横向</el-checkbox>
        </el-form-item>
        <el-form-item label="每页">
          <el-input-number v-model="cols" :min="1" :max="8" size="small" style="width: 90px" />
          ×
          <el-input-number v-model="rows" :min="1" :max="8" size="small" style="width: 90px" />
          <el-button text size="small" @click="applyPreset('A4-3x3')">A4 3×3</el-button>
          <el-button text size="small" @click="applyPreset('Letter-2x3')">Letter 2×3</el-button>
        </el-form-item>
        <el-form-item label="页边距/间距">
          <el-input-number v-model="marginMm" :min="0" :max="30" :precision="1" size="small"
            style="width: 90px" />
          /
          <el-input-number v-model="gapMm" :min="0" :max="20" :precision="1" size="small"
            style="width: 90px" /> mm
        </el-form-item>
        <el-form-item label="背面对齐">
          <el-select v-model="backMode" style="width: 130px">
            <el-option value="none" label="不要背面" />
            <el-option value="mirror" label="镜像排布" />
            <el-option value="template" label="指定背面模板" />
          </el-select>
          <el-select v-if="backMode === 'template'" v-model="backTemplateId"
            style="width: 150px; margin-left: 6px">
            <el-option v-for="t in templates" :key="t.id" :label="t.name" :value="t.id" />
          </el-select>
        </el-form-item>
        <div v-if="checkMsg" class="hint" :class="{ bad: checkBad }">{{ checkMsg }}</div>
      </template>
    </el-form>

    <div v-if="busy" class="progress">
      <el-progress :percentage="pct" :status="state.cancelled ? 'exception' : undefined" />
      <div class="hint2">{{ state.label }} （{{ state.done }}/{{ state.total }}）</div>
      <el-button size="small" style="margin-top: 8px" @click="cancelled = true">中断</el-button>
    </div>

    <template #footer>
      <el-button size="small" :disabled="busy" @click="visible = false">取消</el-button>
      <el-button size="small" type="primary" :disabled="busy || !targets.length" @click="run">
        导出 {{ targets.length }} 张
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api/client'
import {
  exportImposedPdf, exportOne, exportZip, imposeCheck,
  DPI_PRESETS, PAPERS, type BleedMode, type BatchProgress
} from '../render/exporter'

const props = defineProps<{
  modelValue: boolean
  pid: string
  /** 单张模式：只导出这张卡 */
  cardId?: string
  /** 批量模式可选：限定的卡牌 id（如勾选/筛选结果）；不传=全部 */
  cardIds?: string[]
  templates: any[]
}>()
const emit = defineEmits(['update:modelValue'])

const singleMode = computed(() => !!props.cardId)
const visible = computed({
  get: () => props.modelValue,
  set: (v: boolean) => emit('update:modelValue', v)
})

const allCards = ref<any[]>([])
const idList = computed(() => props.cardIds ?? [])
const scope = ref<'all' | 'ids'>('all')

const output = ref('image')
const imgFormat = ref('png')
const dpi = ref<number>(300)
const bleedMode = ref<BleedMode>('trim')
const bleedShare = ref<'shared' | 'independent'>('shared')
const cutLines = ref(true)
const transparent = ref(false)
const pattern = ref('{{template}}_{{name}}')
const withData = ref(false)
const groupByTemplate = ref(true)

const paper = ref('A4')
const landscape = ref(false)
const cols = ref(3)
const rows = ref(3)
const marginMm = ref(10)
const gapMm = ref(2)
const backMode = ref<'none' | 'mirror' | 'template'>('none')
const backTemplateId = ref('')

const busy = ref(false)
const cancelled = ref(false)
const state = ref<BatchProgress>({ done: 0, total: 0, label: '', cancelled: false })

const tplMap = computed(() =>
  Object.fromEntries(props.templates.map((t: any) => [t.id, t])))
const tpl0 = computed(() => props.templates[0] || null)
const netSize = computed(() => {
  const t = tpl0.value
  if (!t) return ''
  const d = t.canvas?.dpi ?? 300
  return `${(t.canvas.w / d * 25.4).toFixed(0)}×${(t.canvas.h / d * 25.4).toFixed(0)} mm`
})
const fullSize = computed(() => {
  const t = tpl0.value
  if (!t) return ''
  const d = t.canvas?.dpi ?? 300
  return `${((t.canvas.w + 72) / d * 25.4).toFixed(0)}×${((t.canvas.h + 72) / d * 25.4).toFixed(0)} mm`
})

const targets = computed(() => {
  if (singleMode.value) return allCards.value.filter((c: any) => c.id === props.cardId)
  if (scope.value === 'ids') return allCards.value.filter((c: any) => idList.value.includes(c.id))
  return allCards.value
})

// 纸张放得下吗
const checkMsg = computed(() => {
  if (output.value !== 'pdf' || singleMode.value || !tpl0.value) return ''
  const { cw, ch } = imposeCheck(tpl0.value, {
    paper: paper.value, landscape: landscape.value, cols: cols.value, rows: rows.value,
    marginMm: marginMm.value, gapMm: gapMm.value, bleedMode: bleedMode.value,
    bleedShare: bleedShare.value, dpi: dpi.value
  })
  if (cw < 0 || ch < 0)
    return `放不下！横向差 ${(-Math.min(cw, 0)).toFixed(1)}mm / 纵向差 ${(-Math.min(ch, 0)).toFixed(1)}mm，请减少行列或减小出血`
  return `横向还剩 ${cw.toFixed(1)}mm，纵向还剩 ${ch.toFixed(1)}mm`
})
const checkBad = computed(() => checkMsg.value.startsWith('放不下'))
const pct = computed(() => state.value.total
  ? Math.round(state.value.done / state.value.total * 100) : 0)

function applyPreset(name: string) {
  if (name === 'A4-3x3') { paper.value = 'A4'; cols.value = 3; rows.value = 3; landscape.value = false }
  if (name === 'Letter-2x3') { paper.value = 'Letter'; cols.value = 2; rows.value = 3; landscape.value = false }
}

watch(visible, async (v) => {
  if (!v) return
  cancelled.value = false
  busy.value = false
  const p = new URLSearchParams({ full: '1' })
  allCards.value = await api.get(`/projects/${props.pid}/cards?${p}`)
  if (!singleMode.value && !idList.value.length) scope.value = 'all'
  if (!backTemplateId.value && props.templates[0]) backTemplateId.value = props.templates[0].id
  output.value = singleMode.value ? 'image' : 'zip'
})

async function run() {
  if (!targets.value.length) return ElMessage.warning('没有要导出的卡牌')
  if (checkBad.value) return ElMessage.error('当前纸张放不下这些卡，请先调整')
  busy.value = true
  cancelled.value = false
  state.value = { done: 0, total: targets.value.length, label: '', cancelled: false }
  const onProgress = (p: BatchProgress) => { state.value = p }
  const shouldCancel = () => cancelled.value
  try {
    if (singleMode.value) {
      // E1：单张 PNG / JPG / 单页 PDF
      const card = targets.value[0]
      await exportOne(tplMap.value[card.templateId], card, {
        output: imgFormat.value as any, dpi: dpi.value, bleedMode: bleedMode.value,
        transparent: transparent.value, cutLines: cutLines.value
      })
    } else if (output.value === 'zip') {
      await exportZip(tplMap.value, targets.value, {
        dpi: dpi.value, bleedMode: bleedMode.value, pattern: pattern.value,
        withData: withData.value, groupByTemplate: groupByTemplate.value
      }, onProgress, shouldCancel)
    } else {
      await exportImposedPdf(tplMap.value, targets.value, {
        dpi: dpi.value, bleedMode: bleedMode.value, paper: paper.value,
        landscape: landscape.value, rows: rows.value, cols: cols.value,
        marginMm: marginMm.value, gapMm: gapMm.value, bleedShare: bleedShare.value,
        cutLines: cutLines.value, backMode: backMode.value,
        backTemplateId: backTemplateId.value
      }, onProgress, shouldCancel)
    }
    if (!cancelled.value) ElMessage.success('导出完成')
    visible.value = false
  } catch (e: any) {
    ElMessage.error(e?.message || '导出失败')
  } finally {
    busy.value = false
  }
}
</script>

<style scoped>
.hint { font-size: 12px; color: var(--muted); line-height: 1.4; }
.hint.bad { color: #e5434a; }
.hint2 { font-size: 12px; color: var(--muted); margin-left: 8px; }
.progress { padding-top: 6px; }
</style>
