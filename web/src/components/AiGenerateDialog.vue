<template>
  <el-dialog
    :model-value="modelValue"
    :title="kind === 'baseplate' ? 'AI 生成底板' : 'AI 生成配图'"
    width="680px"
    @update:model-value="v => emit('update:modelValue', v)"
    @open="reload">

    <div class="ai-gen">
      <div class="meta-line">
        <el-tag size="small" type="info">目标尺寸 {{ preview.size || '—' }}</el-tag>
        <el-tag v-if="kind === 'baseplate'" size="small" type="success">
          带布局参考图（含出血，图生图）
        </el-tag>
        <!-- 模板里打开了「底板 → 进 AI 参考图」：参考图会垫上现有底板，属于"改良"而非重画 -->
        <el-tag v-if="kind === 'baseplate' && preview.refBase" size="small" type="warning">
          基于现有底板改良
        </el-tag>
        <span class="muted">{{ kind === 'baseplate'
          ? '底板只出外壳：图片位留空，配图到卡牌页面单独生成'
          : '尺寸取自该图片区域，prompt 已带上卡面文字' }}</span>
      </div>

      <el-form-item label="临时补充" label-width="72px" style="margin-bottom:8px">
        <el-input v-model="extra" type="textarea" :rows="2" maxlength="200" show-word-limit
                  placeholder="可选。如：整体偏暖的金色调、夜里营火的光感（只影响这一次生成）" />
      </el-form-item>

      <div class="row">
        <el-form-item label="候选数" label-width="72px" style="margin-bottom:0">
          <el-radio-group v-model="n" size="small">
            <el-radio-button :value="1">1</el-radio-button>
            <el-radio-button :value="2">2</el-radio-button>
            <el-radio-button :value="4">4</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <div class="spacer" />
        <el-button link @click="showPrompt = !showPrompt">
          {{ showPrompt ? '收起提示词' : '查看提示词' }}
        </el-button>
      </div>

      <pre v-if="showPrompt" class="prompt-box">{{ preview.prompt }}</pre>
      <div v-if="showPrompt && preview.negative_prompt" class="neg">
        负向词：{{ preview.negative_prompt }}
      </div>

      <div class="notice">
        提交后转入后台生成（约 1–2 分钟）。生成完毕后到
        <em>{{ kind === 'baseplate' ? '「底板」→「从资源库中选择」' : '图片字段的「从资源库选择」' }}</em>即可。
      </div>
    </div>

    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="submit">
        开始后台生成（{{ n }} 张）
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api/client'
import { trackAiJob } from '../composables/aiJobs'

const props = defineProps<{
  modelValue: boolean
  pid: string
  kind: 'baseplate' | 'cardart'
  templateId?: string
  cardId?: string
  fieldKey?: string
  /** 通知文案里的名字（模板名 / 卡名） */
  label?: string
}>()
const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'submitted', jobId: string): void
}>()

const extra = ref('')
const n = ref(4)
const showPrompt = ref(false)
const submitting = ref(false)
const preview = ref<any>({ prompt: '', negative_prompt: '', size: '' })
let debounce: number | undefined

async function reload() {
  if (!props.modelValue) return
  extra.value = ''
  submitting.value = false
  await fetchPreview()
}

async function fetchPreview() {
  try {
    preview.value = await api.post(`/projects/${props.pid}/preview-prompt`, {
      kind: props.kind, templateId: props.templateId, cardId: props.cardId,
      fieldKey: props.fieldKey || '', extra: extra.value
    })
  } catch (e: any) {
    ElMessage.error(e?.message || '提示词预览失败')
  }
}

watch(extra, () => {
  window.clearTimeout(debounce)
  debounce = window.setTimeout(fetchPreview, 400)
})

async function submit() {
  submitting.value = true
  try {
    const path = props.kind === 'baseplate' ? 'baseplate' : 'cardart'
    const r = await api.post(`/projects/${props.pid}/ai/${path}`, {
      templateId: props.templateId, cardId: props.cardId, fieldKey: props.fieldKey || '',
      n: n.value, extra: extra.value
    })
    // 交给全局跟踪：完成/失败都会弹通知，用户不用守着这个弹窗
    trackAiJob(r.jobId, {
      pid: props.pid,
      kind: props.kind,
      label: props.label || (props.kind === 'baseplate' ? '底板' : '配图')
    })
    emit('submitted', r.jobId)
    emit('update:modelValue', false)
  } catch (e: any) {
    ElMessage.error(e?.message || '提交失败')
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.ai-gen { min-height: 60px; }
.meta-line { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 10px; }
.meta-line .muted { font-size: 12px; color: var(--muted); }
.row { display: flex; align-items: center; gap: 8px; }
.spacer { flex: 1; }
.prompt-box {
  background: var(--fill-soft); border: 1px solid var(--border); border-radius: 6px;
  padding: 10px; font-size: 12px; line-height: 1.6; white-space: pre-wrap;
  max-height: 240px; overflow: auto; margin: 8px 0 4px;
}
.neg { font-size: 12px; color: var(--muted); margin-bottom: 6px; }
.notice {
  margin-top: 10px; background: var(--info-bg); border: 1px solid var(--info-border); border-radius: 6px;
  padding: 8px 10px; font-size: 12px; line-height: 1.7; color: var(--info-text);
}
.notice em { font-style: normal; color: var(--accent); font-weight: 600; }
.muted { color: var(--muted); }
</style>
