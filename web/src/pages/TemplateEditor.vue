<template>
  <div class="editor" v-loading="loading">
    <!-- 顶部工具条 -->
    <div class="toolbar">
      <el-input v-model="tpl.name" style="width: 180px" @change="mark" />
      <el-tag size="small" type="info">{{ W }}×{{ H }} @{{ tpl.canvas?.dpi }}dpi</el-tag>

      <el-button-group>
        <el-button size="small" :disabled="!canUndo" title="撤销 Ctrl+Z" @click="undo">↶</el-button>
        <el-button size="small" :disabled="!canRedo" title="重做 Ctrl+Shift+Z" @click="redo">↷</el-button>
      </el-button-group>

      <el-button-group>
        <el-button size="small" title="缩小（Ctrl/⌘ + 滚轮，或触摸板双指捏合）"
                   @click="zoom = Math.max(0.2, +(zoom - 0.1).toFixed(2))">－</el-button>
        <el-button size="small" title="适应窗口" @click="fit">{{ Math.round(zoom * 100) }}%</el-button>
        <el-button size="small" title="放大（Ctrl/⌘ + 滚轮，或触摸板双指捏合）"
                   @click="zoom = Math.min(3, +(zoom + 0.1).toFixed(2))">＋</el-button>
      </el-button-group>

      <el-divider direction="vertical" />

      <el-checkbox v-model="wireframe" @change="redraw">字段线框</el-checkbox>
      <el-checkbox v-model="bleedMode" @change="onBleedChange">含出血视图</el-checkbox>
      <el-checkbox v-model="snapEnabled">吸附</el-checkbox>

      <el-button-group>
        <el-button size="small" title="左对齐" @click="align('left')">⇤</el-button>
        <el-button size="small" title="水平居中" @click="align('hcenter')">↔</el-button>
        <el-button size="small" title="右对齐" @click="align('right')">⇥</el-button>
        <el-button size="small" title="顶对齐" @click="align('top')">⇡</el-button>
        <el-button size="small" title="垂直居中" @click="align('vcenter')">↕</el-button>
        <el-button size="small" title="底对齐" @click="align('bottom')">⇣</el-button>
      </el-button-group>

      <div class="spacer" />
      <el-button size="small" @click="addField">＋字段</el-button>
      <el-button size="small" @click="addLayer">＋矩形图层</el-button>
      <!-- 底板：本地上传 / 从资源库挑（AI 生成的图就在资源库里） -->
      <el-dropdown size="small" @command="onBaseplateCmd">
        <el-button size="small">
          底板 ▾
        </el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="upload">本地上传…</el-dropdown-item>
            <el-dropdown-item command="library">从资源库中选择…</el-dropdown-item>
            <el-dropdown-item command="ai">AI 生成底板…</el-dropdown-item>
            <el-dropdown-item command="mask" divided>挖空底板区域…</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <el-button size="small" type="primary" :disabled="!dirty" @click="save">保存</el-button>
      <el-button size="small" @click="router.back()">返回</el-button>
    </div>

    <div class="body">
      <!-- 左：图层 / 字段结构（可拖拽排序） -->
      <aside class="side left">
        <div class="side-title">图层（拖动排序）</div>
        <el-scrollbar>
          <div
            v-for="(l, i) in tpl.layers ?? []" :key="l.id"
            class="item" :class="{ active: sel?.id === l.id }"
            draggable="true"
            @click="selectById('layer', l.id)"
            @dragstart="onDragStart('layer', l, $event)"
            @dragover.prevent
            @drop="onDrop('layer', l, $event)"
            @dragend="onDragEnd">
            <span class="dot" style="background:#c2a04a"></span>
            <span class="label">{{ l.name }}</span>
            <span class="ops">
              <span class="op" title="上移" @click.stop="move('layer', i, -1)">↑</span>
              <span class="op" title="下移" @click.stop="move('layer', i, 1)">↓</span>
              <span class="op" :title="l.visible === false ? '已隐藏' : '可见'"
                    @click.stop="toggleVisible(l)">{{ l.visible === false ? '◌' : '◉' }}</span>
              <span class="op" :title="l.locked ? '已锁定' : '未锁定'"
                    @click.stop="toggleLock(l)">{{ l.locked ? '🔒' : '🔓' }}</span>
            </span>
          </div>

          <div class="side-title" style="margin-top:10px">字段（拖动排序）</div>
          <div
            v-for="(f, i) in sortedFields" :key="f.id"
            class="item" :class="{ active: sel?.id === f.id }"
            draggable="true"
            @click="selectById('field', f.id)"
            @dragstart="onDragStart('field', f, $event)"
            @dragover.prevent
            @drop="onDrop('field', f, $event)"
            @dragend="onDragEnd">
            <span class="dot" :style="{ background: colorOf(f.kind) }"></span>
            <span class="label">{{ f.label || f.key }}</span>
            <el-tag v-if="f.binding === 'fixed'" size="small" effect="plain" class="mini-tag">固定</el-tag>
            <span class="ops">
              <span class="op" title="上移" @click.stop="move('field', i, -1)">↑</span>
              <span class="op" title="下移" @click.stop="move('field', i, 1)">↓</span>
            </span>
            <span class="kind">{{ f.kind }}</span>
          </div>
        </el-scrollbar>
      </aside>

      <!-- 中：画布 -->
      <div class="stage" ref="stageEl">
        <div class="canvas-wrap" :style="{ width: CW * zoom + 'px', height: CH * zoom + 'px' }">
          <canvas ref="canvasEl"></canvas>
          <div v-if="bleedMode" class="bleed-hint">
            虚线内为裁切框（净尺寸 {{ W }}×{{ H }}），绿色为 2mm 安全框
          </div>
        </div>
      </div>

      <!-- 右：属性 -->
      <aside class="side right" @focusin="captureState" @mousedown="captureState">
        <div v-if="!sel" class="empty" style="padding:24px 8px">
          在画布或左侧列表中选择一个元素
        </div>

        <template v-else-if="selObj?.kind === 'field'">
          <div class="side-title">字段属性</div>
          <el-form label-width="70px" size="small">
            <el-form-item label="字段 key"><el-input v-model="selField.key" @change="mark" /></el-form-item>
            <el-form-item label="显示名"><el-input v-model="selField.label" @change="mark" /></el-form-item>
            <el-form-item label="类型">
              <el-select v-model="selField.kind" @change="mark">
                <el-option v-for="k in KINDS" :key="k" :label="k" :value="k" />
              </el-select>
            </el-form-item>
            <!-- 注：radio-group / color-picker / slider 的根元素是 div（不是表单控件），
                 Element Plus 会把 "<label for>" 指向它 → Chrome 报
                 "Incorrect use of <label for=FORM_ELEMENT>"。这些组件自身已通过
                 aria-labelledby 关联标签，所以这里显式 :for="''" 让 EP 渲染 div 而非 label。 -->
            <el-form-item label="绑定" :for="''">
              <el-radio-group v-model="selField.binding" @change="mark">
                <el-radio value="editable">可编辑</el-radio>
                <el-radio value="fixed">模板固定</el-radio>
              </el-radio-group>
            </el-form-item>
            <el-form-item v-if="selField.binding === 'fixed'" label="固定值">
              <el-input v-model="selField.value" @change="mark" />
            </el-form-item>
            <el-divider content-position="left">位置</el-divider>
            <el-form-item label="X"><el-input-number v-model="rect[0]" @change="applyRect" :controls="false" /></el-form-item>
            <el-form-item label="Y"><el-input-number v-model="rect[1]" @change="applyRect" :controls="false" /></el-form-item>
            <el-form-item label="宽"><el-input-number v-model="rect[2]" @change="applyRect" :controls="false" /></el-form-item>
            <el-form-item label="高"><el-input-number v-model="rect[3]" @change="applyRect" :controls="false" /></el-form-item>
            <template v-if="isTextKind">
              <el-divider content-position="left">文本样式</el-divider>
              <el-form-item label="字体">
                <FontPicker v-model="selField.style.fontFamily" @change="mark" />
              </el-form-item>
              <el-form-item label="字号"><el-input-number v-model="selField.style.fontSize" @change="mark" /></el-form-item>
              <el-form-item label="字重">
                <el-select v-model="selField.style.weight" @change="mark">
                  <el-option :value="400" label="常规" /><el-option :value="700" label="粗体" />
                </el-select>
              </el-form-item>
              <el-form-item label="竖排">
                <el-switch v-model="selField.style.vertical" @change="mark" />
              </el-form-item>
              <el-form-item label="颜色" :for="''">
              <el-color-picker v-model="selField.style.color" @change="mark" />
            </el-form-item>
              <el-form-item label="描边">
                <el-color-picker v-model="selField.style.stroke" @change="mark" />
                <el-input-number v-model="selField.style.strokeWidth" size="small" style="width:70px;margin-left:6px" @change="mark" />
              </el-form-item>
              <el-form-item label="行高"><el-input-number v-model="selField.style.lineHeight" :step="0.1" :precision="2" @change="mark" /></el-form-item>
              <el-form-item label="字距"><el-input-number v-model="selField.style.letterSpacing" @change="mark" /></el-form-item>
              <el-form-item label="水平" :for="''">
                <el-radio-group v-model="selField.style.align" @change="mark">
                  <el-radio value="left">左</el-radio><el-radio value="center">中</el-radio><el-radio value="right">右</el-radio>
                </el-radio-group>
              </el-form-item>
              <el-form-item label="垂直" :for="''">
                <el-radio-group v-model="selField.style.valign" @change="mark">
                  <el-radio value="top">上</el-radio><el-radio value="middle">中</el-radio><el-radio value="bottom">下</el-radio>
                </el-radio-group>
              </el-form-item>
              <el-form-item label="自动缩放">
                <el-switch v-model="selField.style.autoShrink" @change="mark" />
              </el-form-item>
              <el-form-item v-if="selField.style.autoShrink !== false" label="最小字号">
                <el-input-number v-model="selField.style.minFontSize" @change="mark" />
              </el-form-item>
            </template>
            <el-divider content-position="left">可见性</el-divider>
            <el-form-item label="定位框" :for="''">
              <el-switch v-model="selField.guide" @change="mark" />
              <span class="hint-inline">卡牌与导出都不渲染，仅编辑器内标注（AI 底板用）</span>
            </el-form-item>
            <el-divider content-position="left">约束</el-divider>
            <el-form-item label="类型">
              <el-select v-model="selField.constraint.type" @change="mark">
                <el-option v-for="t in ['string', 'int', 'float', 'enum', 'bool']" :key="t" :label="t" :value="t" />
              </el-select>
            </el-form-item>
            <el-form-item v-if="selField.constraint.type === 'int' || selField.constraint.type === 'float'" label="范围">
              <el-input-number v-model="selField.constraint.min" size="small" style="width:70px" @change="mark" />
              ~
              <el-input-number v-model="selField.constraint.max" size="small" style="width:70px" @change="mark" />
            </el-form-item>
            <el-form-item v-if="selField.constraint.type === 'enum'" label="枚举值">
              <el-input v-model="enumText" placeholder="逗号分隔" @change="applyEnum" />
            </el-form-item>
          </el-form>
          <el-button type="danger" text size="small" @click="removeSel">删除字段</el-button>
        </template>

        <template v-else>
          <div class="side-title">图层属性</div>
          <el-form label-width="70px" size="small">
            <el-form-item label="名称"><el-input v-model="selLayer.name" @change="mark" /></el-form-item>
            <el-form-item label="X"><el-input-number v-model="rect[0]" @change="applyRect" :controls="false" /></el-form-item>
            <el-form-item label="Y"><el-input-number v-model="rect[1]" @change="applyRect" :controls="false" /></el-form-item>
            <el-form-item label="宽"><el-input-number v-model="rect[2]" @change="applyRect" :controls="false" /></el-form-item>
            <el-form-item label="高"><el-input-number v-model="rect[3]" @change="applyRect" :controls="false" /></el-form-item>
            <el-form-item label="填充" :for="''">
              <el-color-picker v-model="selLayer.fill" @change="mark" />
            </el-form-item>
            <el-form-item label="描边" :for="''">
              <el-color-picker v-model="selLayer.stroke" @change="mark" />
            </el-form-item>
            <el-form-item label="线宽"><el-input-number v-model="selLayer.strokeWidth" @change="mark" /></el-form-item>
            <el-form-item label="圆角"><el-input-number v-model="selLayer.radius" @change="mark" /></el-form-item>
            <el-form-item label="不透明" :for="''">
              <el-slider v-model="selLayer.opacity" :min="0" :max="1" :step="0.05" @change="mark" />
            </el-form-item>
            <el-form-item label="锁定"><el-switch v-model="selLayer.locked" @change="mark" /></el-form-item>
            <el-form-item label="定位框" :for="''">
              <el-switch v-model="selLayer.guide" @change="mark" />
              <span class="hint-inline">卡牌与导出都不渲染，仅编辑器内标注</span>
            </el-form-item>
          </el-form>
          <el-button type="danger" text size="small" @click="removeSel">删除图层</el-button>
        </template>
      </aside>
    </div>

    <input ref="fileEl" type="file" accept="image/*" hidden @change="onFile" />

    <!-- AI 生成底板：提交后转后台，完成后弹通知引导到「底板 → 从资源库中选择」 -->
    <AiGenerateDialog v-model="aiOpen" :pid="pid" kind="baseplate" :template-id="tid"
                      :label="tpl.name" />

    <!-- 从资源库选底板（AI 刚生成的排在最前） -->
    <AssetPickerDialog v-model="showPicker" type="baseplate" @picked="onPickBaseplate" />

    <!-- 本地上传底板：先裁到「净尺寸 + 2×出血」的整张比例，渲染器就能 1:1 对齐 -->
    <ImageCropDialog v-model="showCrop" :file="cropFile" :aspect="bleedRatio"
                     aspect-text="含出血整张" @cropped="onCropped" />

    <!-- 挖空底板：框出若干矩形，这些地方不画底板（导出 PNG 勾"透明背景"即真透明） -->
    <BaseplateMaskDialog v-model="showMask" :tpl="tpl" @apply="onMaskApply" />
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Canvas } from 'fabric'
import { ElMessage } from 'element-plus'
import { api } from '../api/client'
import {
  renderTemplate, rectFromObject, fieldColor, contentSize
} from '../render/templateRenderer'
import { createSnapping } from '../render/snapping'
import FontPicker from '../components/FontPicker.vue'
import ImageCropDialog from '../components/ImageCropDialog.vue'
import BaseplateMaskDialog from '../components/BaseplateMaskDialog.vue'
import { useUnsavedGuard } from '../composables/useUnsavedGuard'
import { useWheelZoom } from '../composables/useWheelZoom'
import AiGenerateDialog from '../components/AiGenerateDialog.vue'
import AssetPickerDialog from '../components/AssetPickerDialog.vue'

const route = useRoute()
const router = useRouter()
const pid = computed(() => route.params.pid as string)
const tid = computed(() => route.params.tid as string)

const KINDS = ['text', 'textarea', 'number', 'enum', 'image', 'icon']

const loading = ref(false)
const dirty = ref(false)
const wireframe = ref(true)
const bleedMode = ref(false)
const snapEnabled = ref(true)
const zoom = ref(0.6)
const tpl = ref<any>({ canvas: { w: 745, h: 1040, dpi: 300, bleed: 36 }, layers: [], fields: [], background: {} })
const sel = ref<any>(null)
const rect = ref<number[]>([0, 0, 0, 0])
const enumText = ref('')
const stageEl = ref<HTMLElement>()
const canvasEl = ref<HTMLCanvasElement>()
const fileEl = ref<HTMLInputElement>()
let canvas: Canvas | null = null
let snapper: { clear: () => void; dispose: () => void } | null = null

const W = computed(() => tpl.value.canvas?.w ?? 745)
const H = computed(() => tpl.value.canvas?.h ?? 1040)
/** 含出血模式下的画布物理尺寸与内容偏移 */
const CW = computed(() => contentSize(tpl.value, bleedMode.value).w)
const CH = computed(() => contentSize(tpl.value, bleedMode.value).h)
const OFF = computed(() => contentSize(tpl.value, bleedMode.value).offset)

const sortedFields = computed(() =>
  [...(tpl.value.fields ?? [])].sort((a: any, b: any) => (a.order ?? 0) - (b.order ?? 0)))
const selObj = computed(() => sel.value)
const selField = computed(() =>
  (tpl.value.fields ?? []).find((f: any) => f.id === sel.value?.id))
const selLayer = computed(() =>
  (tpl.value.layers ?? []).find((l: any) => l.id === sel.value?.id))
const isTextKind = computed(() =>
  ['text', 'textarea', 'number', 'enum'].includes(selField.value?.kind))

const colorOf = fieldColor

// ---- 撤销 / 重做 -----------------------------------------------------------
const undoStack = ref<string[]>([])
const redoStack = ref<string[]>([])
const canUndo = computed(() => undoStack.value.length > 0)
const canRedo = computed(() => redoStack.value.length > 0)

const snapshot = () => JSON.stringify(tpl.value)

function pushHist(snap: string = snapshot()) {
  undoStack.value.push(snap)
  if (undoStack.value.length > 100) undoStack.value.shift()
  redoStack.value = []
}

/**
 * 「改动之前」的快照。
 * 表单控件的 v-model 会先改数据再触发 @change，此时 snapshot() 已经是新值，
 * 直接入栈会导致撤销无效。所以在聚焦/按下鼠标的瞬间先记一份旧状态。
 */
let beforeEdit: string | null = null
function captureState() { if (beforeEdit === null) beforeEdit = snapshot() }
/** 画布上拖动/缩放开始前记录（object:modified 触发时对象已变） */
let beforeDrag: string | null = null

function undo() {
  if (!canUndo.value) return
  redoStack.value.push(snapshot())
  tpl.value = JSON.parse(undoStack.value.pop()!)
  sel.value = null
  beforeEdit = null
  beforeDrag = null
  dirty.value = true
  redraw()
}

function redo() {
  if (!canRedo.value) return
  undoStack.value.push(snapshot())
  tpl.value = JSON.parse(redoStack.value.pop()!)
  sel.value = null
  beforeEdit = null
  beforeDrag = null
  dirty.value = true
  redraw()
}

// ---- 画布 -----------------------------------------------------------------
async function load() {
  loading.value = true
  try {
    tpl.value = await api.get(`/templates/${tid.value}?pid=${pid.value}`)
    await nextTick()
    initCanvas()
    fit()
  } finally { loading.value = false }
}

/**
 * 重绘期间标记：renderTemplate() 内部 canvas.clear() 会走到
 * Canvas.clear() → discardActiveObject() → 触发 'selection:cleared'，
 * 这和「用户主动取消选中」是同一事件，必须区分，否则每次改属性面板都会被清空。
 */
let rendering = false

function initCanvas() {
  snapper?.dispose()
  if (canvas) { canvas.dispose(); canvas = null }
  canvas = new Canvas(canvasEl.value!, {
    width: CW.value * zoom.value, height: CH.value * zoom.value,
    backgroundColor: '#fff', preserveObjectStacking: true
  })
  canvas.setZoom(zoom.value)
  canvas.on('selection:created', onSel)
  canvas.on('selection:updated', onSel)
  canvas.on('selection:cleared', () => { if (!rendering) sel.value = null })
  canvas.on('mouse:down', (e: any) => {
    if (e.target?.data?.kind) beforeDrag = snapshot()
  })
  canvas.on('object:modified', onModified)
  snapper = createSnapping(canvas, {
    width: CW.value,
    height: CH.value,
    zoom: () => zoom.value,
    enabled: () => snapEnabled.value
  })
  redraw()
}

function onSel(e: any) {
  const d = e.selected?.[0]?.data
  sel.value = d?.kind === 'field' || d?.kind === 'layer' ? d : null
  syncRect()
}

function onModified(e: any) {
  // object:modified 触发时几何已经变过了，用按下鼠标那一刻的快照入栈
  if (beforeDrag) { pushHist(beforeDrag); beforeDrag = null }
  syncObject(e.target)
}

/** 把 fabric 对象的位置写回模板数据（减去出血偏移） */
function syncObject(obj: any) {
  const d = obj?.data
  if (!d || !canvas) return
  const r = rectFromObject(obj, OFF.value)
  if (d.kind === 'field') {
    const f = (tpl.value.fields ?? []).find((x: any) => x.id === d.id)
    if (f) f.rect = r
  } else if (d.kind === 'layer') {
    const l = (tpl.value.layers ?? []).find((x: any) => x.id === d.id)
    if (l) l.rect = r
  }
  rect.value = [...r]
  dirty.value = true
}

function syncRect() {
  const t = sel.value?.kind === 'field' ? selField.value : selLayer.value
  rect.value = t ? [...t.rect] : [0, 0, 0, 0]
  if (selField.value) enumText.value = (selField.value.constraint?.options || []).join(',')
}

function selectById(kind: string, id: string) {
  sel.value = { kind, id }
  syncRect()
  const obj = canvas?.getObjects().find((o: any) => o.data?.id === id)
  if (obj && canvas) { canvas.setActiveObject(obj); canvas.requestRenderAll() }
}

let raf = 0
async function redraw() {
  if (!canvas) return
  cancelAnimationFrame(raf)
  raf = requestAnimationFrame(async () => {
    const keepId = sel.value?.id
    rendering = true
    try {
      await renderTemplate(canvas!, tpl.value, {
        wireframe: wireframe.value,
        interactive: true,
        bleedMode: bleedMode.value,
        guides: true,
        editor: true          // 让 guide=true 的隐形定位框在编辑器里可见
      })
    } finally {
      rendering = false
    }
    // 重绘把 fabric 对象全换了（连同选中状态），需要按 id 重新选中
    restoreSelection(keepId)
  })
}

/** 重绘后把选中恢复回去：既能接上「控制面板继续编辑」，也让画布上的控制框不闪掉 */
function restoreSelection(id?: string) {
  if (!canvas) return
  const obj = id ? canvas.getObjects().find((o: any) => o.data?.id === id) : null
  if (obj) {
    // 锁定图层的 selectable=false，强行选中会让它又能被拖动
    if (obj.selectable !== false) canvas.setActiveObject(obj)
    sel.value = { kind: obj.data?.kind, id }
  } else if (id) {
    sel.value = null          // 元素被删了（比如撤销回退到它还存在的状态时）
  }
  canvas.requestRenderAll()
}

function mark() {
  pushHist(beforeEdit ?? snapshot())
  beforeEdit = null
  dirty.value = true
  redraw()
}



function applyRect() {
  const t: any = sel.value?.kind === 'field' ? selField.value : selLayer.value
  if (t) { pushHist(); t.rect = [...rect.value]; dirty.value = true; redraw() }
}

function applyEnum() {
  if (selField.value) {
    pushHist()
    selField.value.constraint.options =
      enumText.value.split(/[,，]/).map((s: string) => s.trim()).filter(Boolean)
    dirty.value = true
  }
}

function onBleedChange() {
  // 画布尺寸随出血模式变化，需要重建尺寸后重绘
  if (canvas) {
    canvas.setDimensions({ width: CW.value * zoom.value, height: CH.value * zoom.value })
    canvas.setZoom(zoom.value)
  }
  snapper?.dispose()
  snapper = canvas ? createSnapping(canvas, {
    width: CW.value, height: CH.value,
    zoom: () => zoom.value, enabled: () => snapEnabled.value
  }) : null
  redraw()
}

/** 对齐到净尺寸区域（含出血时自动加偏移） */
function align(mode: string) {
  const o: any = canvas?.getActiveObject()
  if (!o || !canvas) return
  const r = o.getBoundingRect()
  const offX = r.left - (o.left ?? 0)
  const offY = r.top - (o.top ?? 0)
  const B = OFF.value
  let nx = o.left, ny = o.top
  if (mode === 'left') nx = B - offX
  if (mode === 'right') nx = B + W.value - r.width - offX
  if (mode === 'hcenter') nx = B + (W.value - r.width) / 2 - offX
  if (mode === 'top') ny = B - offY
  if (mode === 'bottom') ny = B + H.value - r.height - offY
  if (mode === 'vcenter') ny = B + (H.value - r.height) / 2 - offY
  pushHist()
  o.set({ left: nx, top: ny })
  o.setCoords()
  syncObject(o)
  canvas.requestRenderAll()
}

function fit() {
  if (!stageEl.value) return
  const avail = stageEl.value.clientWidth - 40
  zoom.value = Math.max(0.15, Math.min(1.5, avail / CW.value))
}

// ---- 结构列表：排序 / 可见性 / 锁定 ---------------------------------------
let dragItem: { kind: string; id: string } | null = null

function onDragStart(kind: string, item: any, e: DragEvent) {
  dragItem = { kind, id: item.id }
  ;(e.currentTarget as HTMLElement)?.classList.add('dragging')
}

function onDragEnd(e: DragEvent) {
  (e.currentTarget as HTMLElement)?.classList.remove('dragging')
  dragItem = null
}

function onDrop(kind: string, target: any, e: DragEvent) {
  e.preventDefault()
  if (!dragItem || dragItem.kind !== kind || dragItem.id === target.id) return
  const arr = kind === 'layer' ? tpl.value.layers : tpl.value.fields
  const from = arr.findIndex((x: any) => x.id === dragItem!.id)
  const to = arr.findIndex((x: any) => x.id === target.id)
  if (from < 0 || to < 0) return
  pushHist()
  const [it] = arr.splice(from, 1)
  arr.splice(to, 0, it)
  if (kind === 'field') arr.forEach((f: any, i: number) => { f.order = i })
  dirty.value = true
  redraw()
}

function move(kind: string, i: number, d: number) {
  const arr = kind === 'layer' ? tpl.value.layers : sortedFields.value
  const list = kind === 'layer' ? tpl.value.layers : tpl.value.fields
  const j = i + d
  if (j < 0 || j >= arr.length) return
  pushHist()
  if (kind === 'layer') {
    const [it] = list.splice(i, 1)
    list.splice(j, 0, it)
  } else {
    const a = arr[i], b = arr[j]
    const tmp = a.order
    a.order = b.order
    b.order = tmp
    list.forEach((f: any, k: number) => { f.order = k })
  }
  dirty.value = true
  redraw()
}

function toggleVisible(l: any) {
  pushHist()
  l.visible = l.visible === false
  dirty.value = true
  redraw()
}

function toggleLock(l: any) {
  pushHist()
  l.locked = !l.locked
  dirty.value = true
  redraw()
}

// ---- 增删 -----------------------------------------------------------------
function addField() {
  const n = (tpl.value.fields?.length ?? 0)
  tpl.value.fields = tpl.value.fields ?? []
  pushHist()
  tpl.value.fields.push({
    id: 'fd_' + Math.random().toString(36).slice(2, 10),
    key: `field_${n + 1}`, label: `字段${n + 1}`, kind: 'text',
    binding: 'editable', rect: [60, 60 + n * 60, 400, 50],
    style: { fontFamily: 'sans-serif',
             fontSize: 32, weight: 400, color: '#1a1a1a', align: 'left', valign: 'top',
             vertical: false, autoShrink: true, minFontSize: 16, lineHeight: 1.2,
             letterSpacing: 0 },
    constraint: { type: 'string', options: [], default: null },
    order: n
  })
  dirty.value = true
  redraw()
}

function addLayer() {
  tpl.value.layers = tpl.value.layers ?? []
  pushHist()
  tpl.value.layers.push({
    id: 'ly_' + Math.random().toString(36).slice(2, 10),
    type: 'rect', name: '新图层', locked: false, visible: true,
    rect: [100, 100, 300, 200], fill: '#e8e8e8', stroke: '#999',
    strokeWidth: 2, radius: 8, opacity: 1
  })
  dirty.value = true
  redraw()
}

function removeSel() {
  if (!sel.value) return
  pushHist()
  if (sel.value.kind === 'field')
    tpl.value.fields = tpl.value.fields.filter((f: any) => f.id !== sel.value.id)
  else
    tpl.value.layers = tpl.value.layers.filter((l: any) => l.id !== sel.value.id)
  sel.value = null
  dirty.value = true
  redraw()
}

async function save() {
  await api.put(`/templates/${tid.value}`, { ...tpl.value, projectId: pid.value })
  dirty.value = false
  ElMessage.success('模板已保存')
}

// 有未保存改动时，站内跳转弹三选、关标签页弹浏览器原生确认
useUnsavedGuard(() => dirty.value, save)

function pickBaseplate() { fileEl.value?.click() }

// ---- 底板：上传 / 资源库 / AI 生成 / 挖空 -----------------------------------
const aiOpen = ref(false)
const showPicker = ref(false)
const showMask = ref(false)

function onBaseplateCmd(cmd: string) {
  if (cmd === 'upload') pickBaseplate()
  else if (cmd === 'library') showPicker.value = true
  else if (cmd === 'ai') aiOpen.value = true
  else if (cmd === 'mask') {
    if (!tpl.value.background?.assetId) return ElMessage.warning('这个模板还没有底板')
    showMask.value = true
  }
}

/** 挖空：把一组矩形写进 background.mask（渲染器负责真正抠掉） */
function onMaskApply(mask: number[][]) {
  const before = snapshot()
  tpl.value.background = { ...(tpl.value.background || {}), mask }
  pushHist(before)
  dirty.value = true
  redraw()
  ElMessage.success(mask.length ? `已挖空 ${mask.length} 块区域` : '已清空挖空区域')
}

/**
 * 统一用后端 apply 端点设置底板 —— 它会带上 `bleedPx`。
 * 若图片实际像素 = 净尺寸 + 2×bleed（AI 生成的那种），渲染器就按 1:1 对齐
 * （出血模式铺满、净尺寸模式从中间裁）；尺寸不符会自动回退 cover，
 * 所以用户手动上传的图走同一条路也不会出问题。
 */
async function onPickBaseplate(assetId: string) {
  const r = await api.post(
    `/projects/${pid.value}/ai/baseplate/apply?templateId=${tid.value}&assetId=${assetId}`)
  const before = snapshot()
  tpl.value.background = r.background || {
    ...(tpl.value.background || {}), assetId, fit: 'cover'
  }
  pushHist(before)
  dirty.value = true
  await redraw()
  ElMessage.success('已应用底板，记得点「保存」')
}

/** 底板按「含出血」的整张比例裁：不然 817×1112 的画布会对图做 cover 再切掉一圈 */
const bleedRatio = computed(() => {
  const { w, h } = contentSize(tpl.value, true)
  return h ? w / h : 0
})

const cropFile = ref<File | null>(null)
const showCrop = ref(false)

function onFile(e: Event) {
  const el = e.target as HTMLInputElement
  const f = el.files?.[0]
  el.value = ''
  if (!f) return
  cropFile.value = f
  showCrop.value = true
}

async function onCropped(blob: Blob) {
  const form = new FormData()
  form.append('file', new File([blob], 'baseplate.png', { type: 'image/png' }))
  form.append('type', 'baseplate')
  const a = await api.upload('/assets/upload', form)
  await onPickBaseplate(a.id)      // 与资源库选择走同一条路（统一带上 bleedPx 判定）
}

// ---- 键盘：撤销重做 / 删除 / 微调 -----------------------------------------
function onKey(e: KeyboardEvent) {
  const tag = (e.target as HTMLElement)?.tagName
  if (tag === 'INPUT' || tag === 'TEXTAREA') return
  const mod = e.ctrlKey || e.metaKey
  if (mod && e.key.toLowerCase() === 'z') {
    e.preventDefault()
    e.shiftKey ? redo() : undo()
    return
  }
  if (mod && e.key.toLowerCase() === 'y') { e.preventDefault(); redo(); return }
  const o: any = canvas?.getActiveObject()
  if (!o || !canvas) return
  if (e.key === 'Delete' || e.key === 'Backspace') { e.preventDefault(); removeSel(); return }
  const step = e.shiftKey ? 10 : 1
  const d: Record<string, number[]> = {
    ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step]
  }
  if (d[e.key]) {
    e.preventDefault()
    pushHist()
    o.set({ left: (o.left ?? 0) + d[e.key][0], top: (o.top ?? 0) + d[e.key][1] })
    o.setCoords()
    syncObject(o)
    canvas.requestRenderAll()
  }
}

watch(zoom, () => {
  if (!canvas) return
  canvas.setDimensions({ width: CW.value * zoom.value, height: CH.value * zoom.value })
  canvas.setZoom(zoom.value)
  canvas.requestRenderAll()
})

// 滚轮 / 触摸板缩放：Ctrl(⌘)+滚轮始终缩放；普通滚轮只在画布滚不动时用来缩放
useWheelZoom({ stage: stageEl, zoom, min: 0.15, max: 3 })

onMounted(() => { load(); window.addEventListener('keydown', onKey) })
onUnmounted(() => {
  window.removeEventListener('keydown', onKey)
  snapper?.dispose()
  canvas?.dispose()
  canvas = null
})
</script>

<style scoped>
.editor { display: flex; flex-direction: column; height: 100%; }
.toolbar {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap; flex: none;
  padding: 8px 14px; background: #fff; border-bottom: 1px solid var(--border);
}
.spacer { flex: 1; }
.body { flex: 1; display: flex; min-height: 0; }
.side {
  width: 270px; flex: none; background: #fff; overflow: hidden;
  border-right: 1px solid var(--border);
}
.side.right { border-right: none; border-left: 1px solid var(--border); padding: 12px; overflow: auto; }
.side-title { font-size: 12px; font-weight: 700; color: var(--muted); padding: 10px 12px 6px; }
.item {
  display: flex; align-items: center; gap: 6px;
  padding: 6px 12px; cursor: pointer; font-size: 13px;
  border-left: 3px solid transparent;
}
.item:hover { background: #f5f6f8; }
.item.active { background: var(--accent-soft); font-weight: 600; border-left-color: var(--accent); }
.item.dragging { opacity: .4; }
.item .label { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dot { width: 8px; height: 8px; border-radius: 50%; flex: none; }
.kind { font-size: 11px; color: var(--muted); }
.mini-tag { transform: scale(.85); }
.ops { display: flex; gap: 6px; color: var(--muted); }
.ops .op { font-size: 13px; cursor: pointer; line-height: 1; }
.ops .op:hover { color: var(--accent); }
.stage { flex: 1; overflow: auto; background: #eceef1; padding: 20px; display: flex; justify-content: center; }
.canvas-wrap { background: #fff; box-shadow: 0 4px 18px rgba(0, 0, 0, .12); align-self: flex-start; position: relative; }
.bleed-hint {
  position: absolute; left: 0; right: 0; bottom: -26px;
  font-size: 11px; color: var(--muted); text-align: center;
}
.hint-inline { margin-left: 10px; font-size: 11px; color: var(--muted); line-height: 1.3; }
</style>
