<!--
  底板挖空编辑器。

  在底板上框出一块块区域，这些地方**不画底板** —— 露出下面的图层/画布底色；
  PNG 导出勾上「透明背景」时就是真正的透明（可做镂空、开窗、异形卡）。

  为什么做成"模板里存一组矩形"而不是直接改图：
    1. 可反复编辑、可撤销、可整块清空 —— 烘焙成新 PNG 就只能从头再来；
    2. 不会往全局共享的 assets 库里灌一堆近似素材；
    3. 渲染器是预览/卡牌页/导出的唯一出处，改一处三处一致。
  坐标存**净尺寸设计坐标**（与其它字段/图层同一套），含出血导出时由渲染器加偏移。
-->
<template>
  <el-dialog :model-value="modelValue" title="编辑底板（挖空区域）" width="780" append-to-body
             :close-on-click-modal="false"
             @update:model-value="(v: boolean) => emit('update:modelValue', v)"
             @opened="onOpen">
    <div v-if="!assetId" class="muted">
      这个模板还没有底板 —— 先用「底板 → 本地上传 / 从资源库中选择 / AI 生成」弄一张，再回来挖空。
    </div>

    <div v-else class="wrap">
      <div ref="boxEl" class="board" :style="{ width: boxW + 'px', height: boxH + 'px' }"
           @pointerdown="onDown" @pointermove="onMove" @pointerup="onUp"
           @pointercancel="onUp">
        <img v-if="placed" class="base" :src="imgSrc" :style="baseStyle" alt="" />
        <div v-for="(r, i) in mask" :key="i" class="hole" :style="holeStyle(r)"
             @pointerdown.stop>
          <span class="del" title="删除这块" @click="removeAt(i)">×</span>
          <span class="idx">{{ i + 1 }}</span>
        </div>
        <div v-if="dragging" class="rubber" :style="holeStyle(dragRect)" />
      </div>

      <div class="side">
        <div class="tip">
          按住拖动框出一块区域，松手即挖空。可以框多块。
        </div>
        <div class="tip muted">
          挖空处在导出 PNG 里是透明的（需勾选导出面板的「透明背景」）；
          编辑器画布底色是白的，所以这里看到的是白色。
        </div>

        <div class="count">{{ mask.length }} 块挖空</div>
        <div class="list">
          <div v-for="(r, i) in mask" :key="i" class="row-item">
            <span class="mono">#{{ i + 1 }}</span>
            <span class="muted mono">
              {{ Math.round(r[0]) }},{{ Math.round(r[1]) }} ·
              {{ Math.round(r[2]) }}×{{ Math.round(r[3]) }}
            </span>
            <span class="spacer" />
            <el-button text size="small" type="danger" @click="removeAt(i)">删</el-button>
          </div>
          <div v-if="!mask.length" class="muted" style="font-size:12px">还没有挖空区域</div>
        </div>

        <div class="row" style="gap:6px; margin-top:8px">
          <el-button size="small" :disabled="!mask.length" @click="undo">撤销上一块</el-button>
          <el-button size="small" :disabled="!mask.length" @click="mask = []">清空</el-button>
        </div>
      </div>
    </div>

    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" @click="apply">
        应用{{ mask.length ? `（${mask.length} 块）` : '（清空）' }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { resolveAsset } from '../api/client'
import { backgroundPlacement } from '../render/templateRenderer'

const props = defineProps<{
  modelValue: boolean
  /** 整个模板对象：只读用它的 canvas / background */
  tpl: any
}>()
const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'apply', mask: number[][]): void
}>()

const boxEl = ref<HTMLElement>()
const mask = ref<number[][]>([])
const natural = ref({ w: 0, h: 0 })
const imgSrc = ref('')
const dragging = ref(false)
const startPt = ref({ x: 0, y: 0 })
const dragRect = ref<number[]>([0, 0, 0, 0])

const MAX_H = 520
const netW = computed(() => Number(props.tpl?.canvas?.w ?? 745))
const netH = computed(() => Number(props.tpl?.canvas?.h ?? 1040))
const boxH = computed(() => MAX_H)
const boxW = computed(() => Math.round(MAX_H * netW.value / netH.value))
/** 显示缩放：设计像素 → 屏幕像素 */
const s = computed(() => boxW.value / netW.value)
const assetId = computed(() => props.tpl?.background?.assetId || '')

/** 与渲染器同一份摆放计算，保证"看到的"就是"挖到的" */
const placed = computed(() => {
  const { w: iw, h: ih } = natural.value
  if (!iw || !ih) return null
  const p = backgroundPlacement(iw, ih, netW.value, netH.value,
    Number(props.tpl?.background?.bleedPx || 0))
  return { ...p, iw }
})

const baseStyle = computed(() => {
  const p = placed.value
  if (!p) return {}
  return {
    left: p.left * s.value + 'px',
    top: p.top * s.value + 'px',
    width: p.iw * p.scale * s.value + 'px'
  }
})

const holeStyle = (r: number[]) => ({
  left: r[0] * s.value + 'px', top: r[1] * s.value + 'px',
  width: r[2] * s.value + 'px', height: r[3] * s.value + 'px'
})

function onOpen() {
  mask.value = JSON.parse(JSON.stringify(props.tpl?.background?.mask || []))
  loadImage()
}

async function loadImage() {
  natural.value = { w: 0, h: 0 }
  const src = resolveAsset(assetId.value)
  if (!src) return
  imgSrc.value = src
  const im = new Image()
  im.crossOrigin = 'anonymous'
  await new Promise(res => { im.onload = res; im.onerror = res; im.src = src })
  natural.value = { w: im.naturalWidth || 0, h: im.naturalHeight || 0 }
}

/** 屏幕坐标 → 设计坐标（并夹在画布内） */
function toDesign(e: PointerEvent) {
  const b = boxEl.value!.getBoundingClientRect()
  const x = (e.clientX - b.left) / s.value
  const y = (e.clientY - b.top) / s.value
  return {
    x: Math.min(netW.value, Math.max(0, x)),
    y: Math.min(netH.value, Math.max(0, y))
  }
}

function rectFrom(a: { x: number, y: number }, b: { x: number, y: number }) {
  const x = Math.min(a.x, b.x), y = Math.min(a.y, b.y)
  return [x, y, Math.abs(b.x - a.x), Math.abs(b.y - a.y)]
}

function onDown(e: PointerEvent) {
  if (!boxEl.value) return
  boxEl.value.setPointerCapture(e.pointerId)
  const p = toDesign(e)
  startPt.value = p
  dragRect.value = [p.x, p.y, 0, 0]
  dragging.value = true
}

function onMove(e: PointerEvent) {
  if (!dragging.value) return
  dragRect.value = rectFrom(startPt.value, toDesign(e))
}

function onUp() {
  if (!dragging.value) return
  dragging.value = false
  const r = dragRect.value
  // 太小的框当作误触（手抖点一下不该挖出一个洞）
  if (r[2] >= 3 && r[3] >= 3) mask.value = [...mask.value, r.map(v => Math.round(v))]
  dragRect.value = [0, 0, 0, 0]
}

function removeAt(i: number) { mask.value.splice(i, 1) }
function undo() { mask.value.pop() }

function apply() {
  emit('apply', JSON.parse(JSON.stringify(mask.value)))
  emit('update:modelValue', false)
}
</script>

<style scoped>
.wrap { display: flex; gap: 16px; }
.board {
  position: relative; flex: none; overflow: hidden; cursor: crosshair;
  background: var(--card); border: 1px solid var(--border); border-radius: 6px;
  box-shadow: var(--shadow-card); touch-action: none;
}
.base { position: absolute; user-select: none; pointer-events: none; }
/* 颜色走 Element Plus 的语义变量（自带暗色主题覆盖），红=危险/删除、蓝=进行中 */
.hole {
  position: absolute; background: rgba(229, 67, 74, .35);
  border: 1px dashed var(--el-color-danger); box-sizing: border-box;
}
.hole .del {
  position: absolute; right: -1px; top: -1px; width: 16px; height: 16px;
  background: var(--el-color-danger); color: #fff; font-size: 12px; line-height: 16px;
  text-align: center; cursor: pointer; border-radius: 0 0 0 4px;
}
.hole .idx {
  position: absolute; left: 2px; top: 0; font-size: 10px; color: #fff;
  text-shadow: 0 0 3px rgba(0, 0, 0, .8);
}
.rubber {
  position: absolute; background: rgba(64, 158, 255, .25);
  border: 1px dashed var(--el-color-primary); box-sizing: border-box;
}
.side { flex: 1; min-width: 0; font-size: 12px; }
.tip { line-height: 1.7; margin-bottom: 6px; }
.count { font-weight: 600; margin: 10px 0 6px; }
.list { max-height: 220px; overflow: auto; }
.row-item { display: flex; align-items: center; gap: 8px; padding: 2px 0; }
.mono { font-family: ui-monospace, Consolas, monospace; font-size: 11px; }
</style>
