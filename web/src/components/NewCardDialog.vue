<!--
  新建卡牌对话框（共用）。

  两个入口都走这里，保证行为一致：
  - 项目页「新建卡牌」/ 模板卡片上的「新建卡牌」
  - 卡牌页工具栏「＋新建卡牌」

  为什么必须让用户选模板，而不能悄悄用「列表第 0 个」：
  模板列表按修改时间排序，刚建的空模板（0 字段）会排在最前，
  这样建出来的卡会挂在一个没有任何字段的模板上，卡牌页一片空白。
  所以默认选中**字段最多**的模板，并在选到空模板时给出警告。
-->
<template>
  <el-dialog :model-value="modelValue" title="新建卡牌" width="540"
             @update:model-value="(v: boolean) => emit('update:modelValue', v)">
    <el-form label-width="86px">
      <el-form-item label="卡牌名称">
        <el-input v-model="name" placeholder="留空则叫「新卡牌」，建好也能改"
                  @keyup.enter="create" />
      </el-form-item>
      <el-form-item label="使用模板">
        <el-select v-model="tid" style="width: 100%">
          <el-option v-for="t in opts" :key="t.id" :value="t.id" :label="t.name">
            <span>{{ t.name }}</span>
            <span class="opt-hint" :class="{ warn: !t.fieldCount }">
              {{ t.fieldCount ? `${t.fieldCount} 个字段` : '还没有字段' }}
              · {{ t.canvas?.w }}×{{ t.canvas?.h }}
            </span>
          </el-option>
        </el-select>
      </el-form-item>
      <el-form-item v-if="picked && !picked.fieldCount" label=" ">
        <span class="warn">
          「{{ picked.name }}」还没有配置字段，卡牌页会是空的 ——
          建议先去模板编辑器加字段。
        </span>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :loading="busy" @click="create">创建并编辑</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '../api/client'

const props = defineProps<{
  modelValue: boolean
  pid: string
  /** 模板列表：项目页给 stats.templates（fieldCount），卡牌页给 /templates（fields） */
  templates: any[]
  /** 预选模板（模板卡片上的按钮传自己、卡牌页传当前卡的模板） */
  defaultTemplateId?: string
}>()
const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'created', card: any): void
}>()

const name = ref('')
const tid = ref('')
const busy = ref(false)

/** 统一两种模板列表的形状：项目页带 fieldCount，卡牌页带 fields */
const opts = computed(() => (props.templates || []).map((t: any) => ({
  id: t.id,
  name: t.name,
  fieldCount: t.fieldCount ?? (t.fields?.length ?? 0),
  canvas: t.canvas
})))

const picked = computed(() => opts.value.find(t => t.id === tid.value))

/** 打开时重置：默认用传入的模板，否则挑字段最多的（避免挂到空模板上） */
watch(() => props.modelValue, (open) => {
  if (!open) return
  const list = opts.value
  if (!list.length) return
  const wanted = props.defaultTemplateId && list.some(t => t.id === props.defaultTemplateId)
    ? props.defaultTemplateId
    : [...list].sort((a, b) => b.fieldCount - a.fieldCount)[0].id
  tid.value = wanted
  name.value = ''
  busy.value = false
})

async function create() {
  if (!tid.value) return ElMessage.warning('请选择模板')
  if (!picked.value?.fieldCount) {
    try {
      await ElMessageBox.confirm(
        `「${picked.value?.name}」还没有配置任何字段，这张卡建出来没有可填内容。要先建吗？`,
        '模板没有字段', { type: 'warning', confirmButtonText: '仍然创建' })
    } catch { return }
  }
  busy.value = true
  try {
    const c = await api.post(`/projects/${props.pid}/cards`,
                             { templateId: tid.value, name: name.value.trim() || '新卡牌' })
    emit('update:modelValue', false)
    emit('created', c)
  } finally { busy.value = false }
}
</script>

<style scoped>
.opt-hint { float: right; margin-left: 12px; font-size: 11px; color: var(--muted); }
.opt-hint.warn { color: #c45656; }
.warn { font-size: 12px; color: #c45656; line-height: 1.5; }
</style>
