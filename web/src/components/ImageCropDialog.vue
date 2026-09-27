<!--
  图片裁切对话框（cropperjs）。

  用途：上传图片时先裁到需要的比例，避免"传进去才发现比例不对"——
  卡图区是 4:3、底板是含出血的卡牌比例，用户原始素材往往不是。

  用法：
  ```vue
  <ImageCropDialog v-model="showCrop" :file="pickedFile" :aspect="4/3"
                   aspect-text="卡图 4:3" @cropped="onCropped" />
  ```
  `aspect = 0` 表示自由裁切（仍可点比例按钮切换）。
-->
<template>
  <el-dialog :model-value="modelValue" title="裁切图片" width="760"
             :close-on-click-modal="false" append-to-body
             @update:model-value="(v: boolean) => emit('update:modelValue', v)"
             @opened="init" @closed="destroy">
    <div class="crop-stage">
      <img ref="imgEl" :src="src" alt="" />
    </div>

    <div class="crop-bar">
      <span class="muted" style="font-size: 12px">比例</span>
      <el-radio-group v-model="ratio" size="small" @change="applyRatio">
        <el-radio-button :value="0">自由</el-radio-button>
        <el-radio-button :value="1">1:1</el-radio-button>
        <el-radio-button :value="16 / 9">16:9</el-radio-button>
        <el-radio-button :value="3 / 4">3:4</el-radio-button>
        <el-radio-button v-if="presetAspect" :value="presetAspect">
          {{ aspectText || '目标比例' }}
        </el-radio-button>
      </el-radio-group>
      <div class="spacer" />
      <span class="muted" style="font-size: 12px">
        {{ size.w }} × {{ size.h }} px
      </span>
      <el-button size="small" @click="reset">重置</el-button>
    </div>

    <div class="muted hint">
      拖拽方框选范围，滚轮或双指缩放；确认后以 PNG 上传（原图不会被修改）。
    </div>

    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :loading="busy" @click="confirm">使用裁切结果</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import Cropper from 'cropperjs'
import 'cropperjs/dist/cropper.css'

const props = withDefaults(defineProps<{
  modelValue: boolean
  /** 待裁切的原始文件 */
  file: File | null
  /** 目标比例 w/h；0 = 自由 */
  aspect?: number
  /** 比例按钮上显示的名字，如「卡图 4:3」 */
  aspectText?: string
}>(), { aspect: 0, aspectText: '' })

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'cropped', blob: Blob): void
}>()

const imgEl = ref<HTMLImageElement>()
const src = ref('')
const ratio = ref(0)
const size = ref({ w: 0, h: 0 })
const busy = ref(false)
/** 预设比例（传给组件的那种）与「自由」区分开：它就是额外多出来的那个按钮 */
const presetAspect = ref(0)

let cropper: Cropper | null = null
let objectUrl = ''

watch(() => props.file, (f) => {
  if (objectUrl) { URL.revokeObjectURL(objectUrl); objectUrl = '' }
  src.value = ''
  if (!f) return
  objectUrl = URL.createObjectURL(f)
  src.value = objectUrl
})

function init() {
  if (!imgEl.value || !src.value) return
  destroy()
  presetAspect.value = props.aspect || 0
  ratio.value = props.aspect || 0
  cropper = new Cropper(imgEl.value, {
    viewMode: 1,             // 不超出画布
    autoCropArea: 1,
    background: true,
    movable: true,
    zoomable: true,
    responsive: true,
    aspectRatio: props.aspect || NaN,
    crop: () => {
      if (!cropper) return
      const d = cropper.getData()
      size.value = { w: Math.round(d.width), h: Math.round(d.height) }
    }
  })
}

function destroy() {
  cropper?.destroy()
  cropper = null
}

function applyRatio(v: any) {
  cropper?.setAspectRatio(Number(v) || NaN)
}

function reset() {
  cropper?.reset()
  applyRatio(ratio.value)
}

async function confirm() {
  if (!cropper) return
  busy.value = true
  try {
    const canvas = cropper.getCroppedCanvas({
      maxWidth: 4096, maxHeight: 4096, imageSmoothingQuality: 'high'
    })
    const blob: Blob | null = await new Promise(res =>
      canvas.toBlob(b => res(b), 'image/png'))
    if (!blob) return
    await nextTick()
    emit('update:modelValue', false)
    emit('cropped', blob)
  } finally { busy.value = false }
}
</script>

<style scoped>
.crop-stage {
  height: 400px; background: #22262c; border-radius: 8px; overflow: hidden;
}
.crop-stage img { max-width: 100%; display: block; }
.crop-bar {
  display: flex; align-items: center; gap: 8px; margin-top: 12px; flex-wrap: wrap;
}
.hint { font-size: 12px; margin-top: 8px; }
:deep(.cropper-view-box) { outline: 2px solid #409eff; outline-color: #409eff; }
</style>
