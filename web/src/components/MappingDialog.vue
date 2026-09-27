<template>
  <el-dialog v-model="visible" title="批量导入（字段映射）" width="900" top="4vh">
    <el-steps :active="step" finish-status="success" simple style="margin-bottom:14px">
      <el-step title="选择来源" />
      <el-step title="字段映射" />
      <el-step title="校验预览" />
    </el-steps>

    <!-- 步骤 1：来源 -->
    <div v-if="step === 0">
      <el-form label-width="90px" size="small">
        <el-form-item label="目标模板">
          <el-select v-model="tplId" style="width:240px" @change="resetMapping">
            <el-option v-for="t in templates" :key="t.id" :label="t.name" :value="t.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="来源" :for="''">
          <el-radio-group v-model="format">
            <el-radio value="csv">CSV / 表格粘贴</el-radio>
            <el-radio value="json">JSON</el-radio>
          </el-radio-group>
          <el-button size="small" style="margin-left:10px" @click="fileEl?.click()">
            选择 .csv / .txt 文件
          </el-button>
          <span class="muted" style="font-size:12px;margin-left:8px">
            从 Excel 直接复制粘贴也可以（自动识别制表符）
          </span>
        </el-form-item>
        <el-form-item label="内容">
          <el-input v-model="text" type="textarea" :rows="12" :placeholder="placeholder" />
        </el-form-item>
        <el-form-item label="导入方式" :for="''">
          <el-radio-group v-model="mode">
            <el-radio value="append">追加</el-radio>
            <el-radio value="replace">替换该模板下全部卡牌</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
    </div>

    <!-- 步骤 2：映射 -->
    <div v-else-if="step === 1">
      <div class="hint">
        共 {{ rows.length }} 行、{{ headers.length }} 列。左列是来源表头，右列选择要写入的字段；
        选「— 忽略 —」表示这一列不导入。
      </div>
      <el-table :data="mappingRows" size="small" max-height="320" border>
        <el-table-column prop="header" label="来源列" width="200" />
        <el-table-column label="预览值" width="200" show-overflow-tooltip>
          <template #default="{ row }">{{ sampleOf(row.header) }}</template>
        </el-table-column>
        <el-table-column label="→ 目标字段">
          <template #default="{ row }">
            <el-select v-model="row.key" size="small" style="width:100%" filterable>
              <el-option label="— 忽略 —" value="" />
              <el-option label="卡名 (name)" value="__name__" />
              <el-option
                v-for="f in editableFields" :key="f.id"
                :label="`${f.label || f.key}（${f.key}）`" :value="f.key" />
            </el-select>
          </template>
        </el-table-column>
      </el-table>
      <div style="margin-top:8px">
        <el-button size="small" @click="autoMap">重新自动匹配</el-button>
      </div>
    </div>

    <!-- 步骤 3：校验预览 -->
    <div v-else>
      <div class="hint">
        <el-tag v-if="!issues.length" type="success" size="small">校验通过</el-tag>
        <el-tag v-else type="warning" size="small">
          {{ issues.length }} 处需要注意（仍可导入，按下方提示处理）
        </el-tag>
        <span style="margin-left:8px">共 {{ rows.length }} 行，将导入 {{ rows.length }} 张卡</span>
      </div>
      <el-table :data="previewRows" size="small" max-height="340" border>
        <el-table-column type="index" label="#" width="46" />
        <el-table-column prop="name" label="卡名" width="140" show-overflow-tooltip />
        <el-table-column
          v-for="f in editableFields" :key="f.id"
          :label="f.label || f.key" min-width="120" show-overflow-tooltip>
          <template #default="{ row, $index }">
            <span :class="{ bad: badCells[`${$index}:${f.key}`] }"
                  :title="badCells[`${$index}:${f.key}`]">
              {{ row.fields[f.key] ?? '—' }}
            </span>
          </template>
        </el-table-column>
      </el-table>
      <el-collapse v-if="issues.length" style="margin-top:10px">
        <el-collapse-item :title="`查看 ${issues.length} 条提示`">
          <div v-for="(i, k) in issues" :key="k" class="issue">
            第 {{ i.row + 1 }} 行 · {{ i.field }}：{{ i.msg }}
          </div>
        </el-collapse-item>
      </el-collapse>
    </div>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button v-if="step > 0" @click="step--">上一步</el-button>
      <el-button v-if="step === 0" type="primary" :disabled="!canNext" @click="goMap">
        下一步
      </el-button>
      <el-button v-else-if="step === 1" type="primary" @click="goPreview">校验</el-button>
      <el-button v-else type="primary" :loading="busy" @click="submit">导入 {{ rows.length }} 张</el-button>
    </template>

    <input ref="fileEl" type="file" accept=".csv,.txt,text/csv" hidden @change="onFile" />
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api/client'

const props = defineProps<{ modelValue: boolean; pid: string; templates: any[]; defaultTpl?: string }>()
const emit = defineEmits<{ (e: 'update:modelValue', v: boolean): void; (e: 'done'): void }>()

const visible = computed({
  get: () => props.modelValue,
  set: (v: boolean) => emit('update:modelValue', v)
})

const step = ref(0)
const busy = ref(false)
const format = ref<'csv' | 'json'>('csv')
const mode = ref('append')
const text = ref('')
const tplId = ref(props.defaultTpl || '')
const headers = ref<string[]>([])
const rows = ref<any[]>([])
const mappingRows = ref<Array<{ header: string; key: string }>>([])
const issues = ref<Array<{ row: number; field: string; msg: string }>>([])
const badCells = ref<Record<string, string>>({})
const fileEl = ref<HTMLInputElement>()

const tpl = computed(() => props.templates.find((t: any) => t.id === tplId.value))
const editableFields = computed(() =>
  (tpl.value?.fields ?? []).filter((f: any) => f.binding !== 'fixed'))
const canNext = computed(() => !!tplId.value && !!text.value.trim())

const placeholder = computed(() => format.value === 'json'
  ? '[{"name":"火球术","cost":3,"desc":"造成 3 点火焰伤害"}]'
  : 'name,cost,desc\n火球术,3,造成 3 点火焰伤害')

watch(() => props.modelValue, (v) => {
  if (v) {
    step.value = 0
    issues.value = []
    if (!tplId.value && props.templates[0]) tplId.value = props.templates[0].id
  }
})

// ---- 解析 ---------------------------------------------------------------
function detectDelim(line: string) {
  if (line.includes('\t')) return '\t'
  if (line.includes(';')) return ';'
  return ','
}

function parseCsv(src: string) {
  const lines = src.replace(/\r\n/g, '\n').split('\n').filter((l) => l.trim() !== '')
  if (!lines.length) return
  const d = detectDelim(lines[0])
  const split = (l: string) => {
    // 支持最简引号包裹（含分隔符）
    const out: string[] = []
    let cur = '', inQ = false
    for (let i = 0; i < l.length; i++) {
      const ch = l[i]
      if (ch === '"') { inQ = !inQ; continue }
      if (ch === d && !inQ) { out.push(cur); cur = ''; continue }
      cur += ch
    }
    out.push(cur)
    return out.map((s) => s.trim())
  }
  headers.value = split(lines[0])
  rows.value = lines.slice(1).map((l) => {
    const cells = split(l)
    const o: any = {}
    headers.value.forEach((h, i) => { o[h] = cells[i] ?? '' })
    return o
  })
}

function parseJson(src: string) {
  const data = JSON.parse(src)
  const arr = Array.isArray(data) ? data : (data.cards || [])
  rows.value = arr
  const set: string[] = []
  for (const r of arr) for (const k of Object.keys(r)) if (!set.includes(k)) set.push(k)
  headers.value = set
}

function goMap() {
  try {
    if (format.value === 'json') parseJson(text.value)
    else parseCsv(text.value)
  } catch (e: any) {
    return ElMessage.error('解析失败：' + (e.message || e))
  }
  if (!rows.value.length) return ElMessage.warning('没有解析到数据行')
  autoMap()
  step.value = 1
}

function sampleOf(h: string) {
  return rows.value[0]?.[h] ?? ''
}

function resetMapping() { /* 换模板后重新自动匹配 */ }

/** 自动匹配：精确 key > 标签 > 中文别名 > 包含 */
function autoMap() {
  const alias: Record<string, string[]> = {
    name: ['name', '卡名', '名称', '卡牌名', '标题', 'title'],
    desc: ['desc', '描述', '效果', '说明', '正文'],
    cost: ['cost', '费用', '消耗'],
    tags: ['tags', '标签', '关键词']
  }
  mappingRows.value = headers.value.map((h) => {
    const lower = h.toLowerCase()
    let key = ''
    for (const f of editableFields.value) {
      if (f.key.toLowerCase() === lower || (f.label && f.label === h)) { key = f.key; break }
    }
    if (!key) {
      for (const [k, names] of Object.entries(alias)) {
        if (names.some((n) => lower === n.toLowerCase())) {
          key = k === 'name' ? '__name__' : (editableFields.value.some((f: any) => f.key === k) ? k : '')
          if (key) break
        }
      }
    }
    if (!key) {
      const hit = editableFields.value.find((f: any) =>
        lower.includes(f.key.toLowerCase()) || (f.label && h.includes(f.label)))
      if (hit) key = hit.key
    }
    return { header: h, key }
  })
}

// ---- 校验预览 -----------------------------------------------------------
const previewRows = computed(() => {
  return rows.value.map((r) => {
    const o: any = { fields: {} as Record<string, any> }
    let name = ''
    for (const m of mappingRows.value) {
      const v = r[m.header]
      if (!m.key) continue
      if (m.key === '__name__') { name = v; continue }
      o.fields[m.key] = v
    }
    o.name = name || r.name || r['卡名'] || '未命名'
    return o
  })
})

function goPreview() {
  issues.value = []
  badCells.value = {}
  const used = mappingRows.value.filter((m) => m.key && m.key !== '__name__').map((m) => m.key)
  if (!mappingRows.value.some((m) => m.key === '__name__') && !rows.value[0]?.name) {
    issues.value.push({ row: 0, field: '卡名', msg: '没有列映射到卡名，将使用「未命名」' })
  }
  const byKey: Record<string, any> = {}
  for (const f of editableFields.value) byKey[f.key] = f

  rows.value.forEach((r, ri) => {
    for (const k of used) {
      const f = byKey[k]
      if (!f) continue
      const raw = r[mappingRows.value.find((m) => m.key === k)!.header]
      const c = f.constraint || {}
      const msg = validate(raw, c, f.kind)
      if (msg) {
        issues.value.push({ row: ri, field: f.label || k, msg })
        badCells.value[`${ri}:${k}`] = msg
      }
    }
  })
  step.value = 2
}

function validate(raw: any, c: any, kind: string) {
  const v = raw == null ? '' : String(raw)
  if (v === '') return c.default == null ? '为空' : ''
  if (kind === 'number' || c.type === 'int' || c.type === 'float') {
    const n = Number(v)
    if (Number.isNaN(n)) return `不是数字：${v}`
    if (c.type === 'int' && !Number.isInteger(Number(v))) return `不是整数：${v}`
    if (c.min != null && n < c.min) return `小于最小值 ${c.min}`
    if (c.max != null && n > c.max) return `大于最大值 ${c.max}`
  }
  if (c.type === 'enum' && (c.options || []).length && !c.options.includes(v)) {
    return `不在枚举内（${c.options.join('/')}）`
  }
  if (c.maxLen && v.length > c.maxLen) return `超过最大长度 ${c.maxLen}`
  return ''
}

// ---- 提交 ---------------------------------------------------------------
async function submit() {
  busy.value = true
  try {
    const mapping: Record<string, string> = {}
    for (const m of mappingRows.value) {
      mapping[m.header] = m.key === '__name__' ? 'name' : m.key
    }
    const r = await api.post(`/projects/${props.pid}/cards/import`, {
      templateId: tplId.value,
      format: format.value === 'json' ? 'json' : 'csv',
      payload: format.value === 'json' ? text.value : toCsvPayload(),
      mapping: format.value === 'json' ? {} : mapping,
      mode: mode.value
    })
    ElMessage.success(`已导入 ${r.created} 张卡`)
    visible.value = false
    emit('done')
  } catch (e: any) {
    ElMessage.error(e.message || '导入失败')
  } finally { busy.value = false }
}

/** JSON 模式直接发原文；CSV 模式把映射后的表头发给后端（后端按 mapping 转换） */
function toCsvPayload() {
  const lines = text.value.replace(/\r\n/g, '\n').split('\n').filter((l) => l.trim() !== '')
  const d = detectDelim(lines[0])
  const split = (l: string) => l.split(d).map((s) => s.trim().replace(/^"|"$/g, ''))
  const srcHeaders = split(lines[0])
  const outHeaders = srcHeaders.map((h) => {
    const m = mappingRows.value.find((x) => x.header === h)
    return m?.key === '__name__' ? 'name' : (m?.key ?? '')
  })
  const body = lines.slice(1).map((l) => split(l).join(','))
  return [outHeaders.join(','), ...body].join('\n')
}

async function onFile(e: Event) {
  const f = (e.target as HTMLInputElement).files?.[0]
  if (!f) return
  text.value = await f.text()
  ;(e.target as HTMLInputElement).value = ''
  ElMessage.success(`已读取 ${f.name}`)
}
</script>

<style scoped>
.hint { font-size: 12px; color: var(--muted); margin-bottom: 8px; }
.bad { color: #e5434a; font-weight: 600; }
.issue { font-size: 12px; padding: 2px 0; color: #b26a00; }
.muted { color: var(--muted); }
</style>
