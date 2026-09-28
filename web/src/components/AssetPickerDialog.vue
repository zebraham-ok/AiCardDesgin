<template>
  <el-dialog
    :model-value="modelValue"
    :title="title"
    width="760px"
    @update:model-value="v => emit('update:modelValue', v)"
    @open="load">
    <div class="row" style="margin-bottom: 10px">
      <el-input v-model="q" placeholder="搜索名称 / 标签" clearable style="width: 220px" />
      <el-select v-if="showLib" v-model="lib" clearable placeholder="全部子库"
                 style="width: 150px" @change="load">
        <el-option v-for="l in libs" :key="l.id" :label="l.name" :value="l.id" />
      </el-select>
      <div class="spacer" />
      <span class="muted" style="font-size: 12px">
        按生成时间倒序，AI 刚生成的会排在最前面
      </span>
    </div>

    <div v-if="loading" class="empty">加载中…</div>
    <div v-else-if="!items.length" class="empty">
      资源库里还没有{{ typeLabel }}。<br />
      <span class="muted">可以用「AI 生成」产出，或从本地上传。</span>
    </div>

    <div v-else class="grid" :class="{ iconish: type === 'icon' }">
      <div v-for="a in items" :key="a.id"
           class="cell" :class="{ picked: picked === a.id }" @click="picked = a.id"
           @dblclick="choose">
        <img :src="thumbUrl(a.id)" />
        <div class="nm">{{ a.name }}</div>
        <div class="sub">{{ a.createdAt?.slice(5, 16).replace('T', ' ') }}
          <span v-if="a.aiProvenance?.model"> · AI</span>
        </div>
      </div>
    </div>

    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :disabled="!picked" @click="choose">使用选中的</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { api, thumbUrl } from '../api/client'

const props = defineProps<{
  modelValue: boolean
  /** 资源类型：底板 / 图片 / 图标 */
  type: 'baseplate' | 'image' | 'icon'
}>()
const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'picked', assetId: string, asset: any): void
}>()

const items = ref<any[]>([])
const loading = ref(false)
const q = ref('')
const lib = ref('')
const libs = ref<any[]>([])
const picked = ref('')

const title = computed(() => ({
  baseplate: '从资源库选择底板', image: '从资源库选择图片', icon: '从资源库选择图标'
}[props.type]))
const typeLabel = computed(() => ({ baseplate: '底板', image: '图片', icon: '图标' }[props.type]))
const showLib = computed(() => props.type === 'icon')

async function load() {
  loading.value = true
  picked.value = ''
  try {
    if (showLib.value) libs.value = await api.get('/asset-libraries')
    const p = new URLSearchParams({ type: props.type })
    if (lib.value) p.set('library', lib.value)
    if (q.value) p.set('q', q.value)
    const list = await api.get(`/assets?${p}`)
    // 生成/上传时间倒序 —— 刚 AI 出来的排最前，省得翻
    items.value = (list || []).sort((a: any, b: any) =>
      String(b.createdAt || '').localeCompare(String(a.createdAt || '')))
  } finally { loading.value = false }
}

function choose() {
  const a = items.value.find(x => x.id === picked.value)
  if (!a) return
  emit('picked', a.id, a)
  emit('update:modelValue', false)
}
</script>

<style scoped>
.grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 10px;
  max-height: 52vh; overflow: auto;
}
.grid.iconish { grid-template-columns: repeat(auto-fill, minmax(96px, 1fr)); }
.cell {
  border: 2px solid var(--border); border-radius: 8px; padding: 6px; cursor: pointer;
  background: var(--panel);
}
.cell:hover { border-color: var(--accent); }
.cell.picked { border-color: var(--accent); background: var(--accent-soft); }
.cell img {
  width: 100%; height: 96px; object-fit: contain; background: var(--panel-soft); border-radius: 4px;
}
.grid.iconish .cell img { height: 48px; }
.cell .nm {
  font-size: 12px; font-weight: 600; margin-top: 5px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.cell .sub { font-size: 11px; color: var(--muted); }
.spacer { flex: 1; }
</style>
