<template>
  <div class="font-picker">
    <el-select
      :model-value="modelValue"
      filterable
      allow-create
      default-first-option
      :filter-method="onFilter"
      :reserve-keyword="false"
      :fit-input-width="false"
      placeholder="搜字体（中英文均可，如 微软雅黑 / YaHei）"
      class="picker"
      @update:model-value="onPick"
      @visible-change="onVisible">
      <el-option-group v-if="pBuiltins.length" label="系统内置">
        <el-option v-for="f in pBuiltins" :key="f.family" :label="f.label" :value="f.family" />
      </el-option-group>

      <el-option-group v-if="pLocals.length" :label="localGroupLabel">
        <el-option v-for="f in pLocals" :key="f.family" :label="f.family" :value="f.family">
          <span>{{ f.family }}</span>
          <span v-if="aliasHint(f)" class="opt-hint">{{ aliasHint(f) }}</span>
        </el-option>
      </el-option-group>

      <el-option-group v-if="pAssets.length" label="自定义字体（已上传，随项目走）">
        <el-option v-for="f in pAssets" :key="f.family" :label="f.label" :value="f.family">
          <span>{{ f.label }}</span>
          <span class="opt-hint">{{ f.error ? '载入失败' : f.loaded ? '' : '未载入' }}</span>
        </el-option>
      </el-option-group>

      <!-- 本机字体可能有几百个，默认只渲染前 N 个，其余靠搜索 -->
      <el-option v-if="hiddenLocals > 0" :value="HINT" disabled
                 :label="`…还有 ${hiddenLocals} 个本机字体，输入关键词搜索`" />

      <!-- 两个动作收进下拉面板最底部：不占输入框下方的位置，字体多了也自然沉底 -->
      <template #footer>
        <div class="dd-footer">
          <el-button link size="small" :loading="scanning" @click="scan">扫描本机字体</el-button>
          <span class="sep">·</span>
          <el-button link size="small" @click="fileEl?.click()">上传字体文件</el-button>
        </div>
      </template>
    </el-select>

    <div v-if="hint" class="hint-line">{{ hint }}</div>

    <input ref="fileEl" type="file" accept=".ttf,.otf,.woff2,.woff,.ttc" hidden @change="onFile" />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  canEnumerateLocalFonts, fontChoices, loadCachedLocalFonts,
  refreshFontList, scanLocalFonts, uploadFont, familyOf, type FontChoice
} from '../render/fonts'
import { aliasesOf, matchFont, rankFont } from '../render/fontAliases'

const props = defineProps<{ modelValue?: string }>()
const emit = defineEmits<{
  (e: 'update:modelValue', v: string): void
  (e: 'change', v: string): void
}>()

/** 一个不可选的提示项（不是真正的字体族名） */
const HINT = '__bgw_hint__'
/** 无关键词时本机字体的渲染上限（几百个 option 会拖慢下拉） */
const LOCAL_LIMIT = 40

const options = ref<FontChoice[]>([])
const keyword = ref('')
const scanning = ref(false)
const fileEl = ref<HTMLInputElement>()

const builtins = computed(() => options.value.filter(f => f.source === 'builtin'))
const localAll = computed(() => options.value.filter(f => f.source === 'local'))
const assets = computed(() => options.value.filter(f => f.source === 'asset'))

/** 关键词命中集合（族名 + 显示名 + 中英文别名 + 额外关键词） */
const matched = computed(() => {
  const q = keyword.value
  if (!q) return null
  return options.value
    .filter(f => matchFont(f, q))
    .sort((a, b) => rankFont(a, q) - rankFont(b, q))
})

const pBuiltins = computed(() =>
  matched.value ? matched.value.filter(f => f.source === 'builtin') : builtins.value)
const pAssets = computed(() =>
  matched.value ? matched.value.filter(f => f.source === 'asset') : assets.value)
const pLocals = computed(() => {
  if (matched.value) return matched.value.filter(f => f.source === 'local')
  return localAll.value.slice(0, LOCAL_LIMIT)
})
const hiddenLocals = computed(() =>
  matched.value ? 0 : Math.max(0, localAll.value.length - LOCAL_LIMIT))

const localGroupLabel = computed(() => {
  const n = localAll.value.length
  if (!n) return '本机已装字体'
  return `本机已装字体（${n}${hiddenLocals.value ? `，仅显示前 ${LOCAL_LIMIT}` : ''}）`
})

/** 本机字体在列表右侧显示它的中文别名，便于识别 */
function aliasHint(f: FontChoice) {
  const a = aliasesOf(f.family)
  return a.length ? a[0] : ''
}

/** 当前选中项的来源提示 */
const hint = computed(() => {
  const f = props.modelValue
  if (!f) return ''
  if (f.startsWith('bgw_')) return '自定义字体：随项目包迁移，跨机可复现'
  if (builtins.value.some(b => b.family === f)) return ''
  if (localAll.value.some(l => l.family === f) || aliasesOf(f).length)
    return '本机字体：不复制文件，换机器/发他人时可能回退'
  return '未知族名：只有本机装了同名字体才会生效'
})

async function reload() {
  await refreshFontList()
  loadCachedLocalFonts()
  options.value = fontChoices()
}

onMounted(reload)

function onFilter(q: string) {
  keyword.value = (q || '').trim()
}

/** 下拉收起时清掉关键词，避免下次展开还是过滤状态 */
function onVisible(v: boolean) {
  if (!v) keyword.value = ''
}

function onPick(v: string) {
  if (v === HINT) return
  emit('update:modelValue', v)
  emit('change', v)
}

async function scan() {
  scanning.value = true
  try {
    const r = await scanLocalFonts()
    await reload()
    if (r.fonts.length) {
      ElMessage.success(`检测到 ${r.fonts.length} 个本机字体`)
    } else {
      await       ElMessageBox.alert(
        '没有检测到可用的本机字体。\n\n' +
        '解决办法：① 在字体框里直接填字体族名（例如 微软雅黑 / SimSun，支持中英文搜索）；' +
        '② 点下拉面板底部的「上传字体文件」，从 C:\\Windows\\Fonts 或任意目录挑选 ttf/otf' +
        '（上传后成为自定义字体，随项目走）。',
        '未找到本机字体', { confirmButtonText: '知道了' })
    }
    if (r.error) {
      ElMessage.warning(r.error)
      if (!canEnumerateLocalFonts()) {
        await ElMessageBox.alert(
          '当前浏览器不支持自动枚举本机字体（该能力仅 Chrome / Edge 103+ 提供）。\n\n' +
          '你仍可以：① 直接输入字体族名；② 上传字体文件（推荐，跨机可复现）。',
          '浏览器不支持自动扫描', { confirmButtonText: '知道了' })
      }
    }
  } finally { scanning.value = false }
}

async function onFile(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return
  try {
    const a = await uploadFont(file)
    await reload()
    onPick(familyOf(a))
    ElMessage.success(`已上传「${a.name}」并改用该字体`)
  } catch (err: any) {
    ElMessage.error(err?.message || '字体上传失败')
  } finally {
    ;(e.target as HTMLInputElement).value = ''
  }
}
</script>

<style scoped>
.font-picker { width: 100%; }
/* 下拉面板比输入框宽，长族名 + 别名提示不会挤在一起 */
.picker :deep(.el-select-dropdown__item) {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
}
.opt-hint { font-size: 11px; color: var(--muted); flex: none; }
.hint-line { margin-top: 2px; font-size: 11px; color: var(--muted); line-height: 1.3; }
.dd-footer {
  display: flex; align-items: center; gap: 6px;
  padding: 4px 10px; border-top: 1px solid var(--border, #ebeef5);
}
.dd-footer .sep { color: var(--el-border-color); font-size: 11px; }
</style>
