<template>
  <div class="panel brief-panel" v-loading="saving">
    <div class="row head">
      <span class="title">项目设定</span>
      <span class="muted sub">创作简报</span>
      <div class="spacer" />
      <template v-if="editing">
        <el-button size="small" @click="cancel">取消</el-button>
        <el-button size="small" type="primary" :loading="saving" @click="save(true)">保存</el-button>
      </template>
      <el-button v-else size="small" type="primary" @click="startEdit">
        {{ briefEmpty ? '填写设定' : '编辑' }}
      </el-button>
    </div>

    <!-- 编辑态：表单直接铺在左栏里（不再走抽屉） -->
    <div v-if="editing" class="edit-body">
      <div class="tip">
        填得越具体，AI 生图 / 生成文案的风格越统一。<strong>关键词</strong>与<strong>禁忌</strong>
        会直接进入提示词，其余字段用于拼装风格、配色与世界观语料。
      </div>

      <el-collapse v-model="open">
        <!-- 基本 -->
        <el-collapse-item name="basic">
          <template #title><span class="sec">基本</span></template>
          <el-form label-width="86px" size="default">
            <el-form-item label="游戏名">
              <el-input v-model="b.title" placeholder="例如：星域争霸" />
            </el-form-item>
            <el-form-item label="副标题">
              <el-input v-model="b.subtitle" placeholder="英文名 / 副标题，可留空" />
            </el-form-item>
            <el-form-item label="一句话卖点">
              <el-input v-model="b.oneLiner" maxlength="60" show-word-limit
                        placeholder="争夺星区资源的快节奏对抗卡牌" />
            </el-form-item>
            <el-form-item label="类型">
              <el-select v-model="b.genre" multiple filterable allow-create
                         default-first-option placeholder="可多选，也可自己输入"
                         style="width: 100%">
                <el-option v-for="g in GENRES" :key="g" :label="g" :value="g" />
              </el-select>
            </el-form-item>
            <el-form-item label="人数">
              <el-select v-model="b.players" filterable allow-create clearable
                         placeholder="选择或输入" style="width: 100%">
                <el-option v-for="p in PLAYER_OPTIONS" :key="p" :label="p" :value="p" />
              </el-select>
            </el-form-item>
            <el-form-item label="时长">
              <el-select v-model="b.playTime" filterable allow-create clearable
                         placeholder="选择或输入" style="width: 100%">
                <el-option v-for="t in TIME_OPTIONS" :key="t" :label="t" :value="t" />
              </el-select>
            </el-form-item>
            <el-form-item label="适龄">
              <el-select v-model="b.age" filterable allow-create clearable
                         placeholder="选择或输入" style="width: 100%">
                <el-option v-for="a in AGE_OPTIONS" :key="a" :label="a" :value="a" />
              </el-select>
            </el-form-item>
          </el-form>
        </el-collapse-item>

        <!-- 世界观 -->
        <el-collapse-item name="world">
          <template #title><span class="sec">世界观</span></template>
          <el-form label-width="86px">
            <el-form-item label="简介">
              <el-input v-model="b.synopsis" type="textarea" :rows="5" maxlength="200"
                        show-word-limit placeholder="旧帝国崩溃后……（200 字以内，会作为文生文的世界观语料）" />
            </el-form-item>
            <el-form-item label="关键词">
              <div class="kw">
                <el-select v-model="b.keywords" multiple filterable allow-create
                           default-first-option placeholder="回车添加；生图与文案的核心语料"
                           style="width: 100%">
                  <el-option v-for="k in keywordPool" :key="k" :label="k" :value="k" />
                </el-select>
                <el-button size="small" text :disabled="!b.synopsis && !b.oneLiner"
                           @click="pickKeywords">从卖点/简介提取候选词</el-button>
              </div>
            </el-form-item>
            <el-form-item label="派系">
              <div class="factions">
                <div v-for="(f, i) in b.factions" :key="i" class="faction-row">
                  <el-color-picker v-model="f.color" size="small" />
                  <el-input v-model="f.name" size="small" placeholder="派系名" style="width: 110px" />
                  <el-input v-model="f.desc" size="small" placeholder="一句话气质/配色，如：重工业、冷灰蓝" />
                  <el-button size="small" text type="danger" @click="b.factions.splice(i, 1)">删除</el-button>
                </div>
                <el-button size="small" @click="addFaction">+ 添加派系</el-button>
              </div>
            </el-form-item>
          </el-form>
        </el-collapse-item>

        <!-- 美术 -->
        <el-collapse-item name="art">
          <template #title><span class="sec">美术</span></template>
          <el-form label-width="86px">
            <el-form-item label="主风格">
              <el-select v-model="b.artStyle.style" filterable allow-create clearable
                         placeholder="选一个或自己写" style="width: 100%">
                <el-option v-for="s in ART_STYLES" :key="s" :label="s" :value="s" />
              </el-select>
            </el-form-item>
            <el-form-item label="氛围">
              <el-select v-model="b.artStyle.mood" multiple filterable allow-create
                         default-first-option placeholder="可多选" style="width: 100%">
                <el-option v-for="m in MOODS" :key="m" :label="m" :value="m" />
              </el-select>
            </el-form-item>
            <el-form-item label="主色板" :for="''">
              <div class="palette">
                <el-color-picker
                  v-for="(c, i) in b.artStyle.palette" :key="i"
                  v-model="b.artStyle.palette[i]" size="small" />
                <el-button v-if="b.artStyle.palette.length < 6" size="small" text
                           @click="b.artStyle.palette.push('#cccccc')">+ 颜色</el-button>
                <el-dropdown v-if="b.artStyle.palette.length" trigger="click" @command="applyPreset">
                  <el-button size="small" text>预设 ▾</el-button>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item v-for="p in PALETTE_PRESETS" :key="p.name" :command="p.name">
                        <span class="swatches">
                          <i v-for="c in p.colors" :key="c" :style="{ background: c }"></i>
                          {{ p.name }}
                        </span>
                      </el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
                <el-button size="small" text type="danger" :disabled="!b.artStyle.palette.length"
                           @click="b.artStyle.palette = []">清空</el-button>
              </div>
            </el-form-item>
            <el-form-item label="参考作品">
              <el-select v-model="b.artStyle.references" multiple filterable allow-create
                         default-first-option placeholder="回车添加，如《沙丘》电影美术"
                         style="width: 100%" />
            </el-form-item>
            <el-form-item label="细节补充">
              <el-input v-model="b.artStyle.details" type="textarea" :rows="3"
                        placeholder="如：笔触粗犷、边缘做旧、避免高饱和霓虹" />
            </el-form-item>
            <el-form-item label="禁忌">
              <el-select v-model="b.taboos" multiple filterable allow-create
                         default-first-option placeholder="直接作为生图负向词"
                         style="width: 100%">
                <el-option v-for="t in TABOOS" :key="t" :label="t" :value="t" />
              </el-select>
            </el-form-item>
          </el-form>
        </el-collapse-item>
      </el-collapse>

      <div class="row foot">
        <span class="muted">{{ savedAt ? `已保存 ${savedAt}` : '改完点右侧「保存」生效' }}</span>
        <div class="spacer" />
        <el-button size="small" @click="cancel">取消</el-button>
        <el-button size="small" type="primary" :loading="saving" @click="save(true)">保存</el-button>
      </div>
    </div>

    <!-- 查看态：设定常驻可见，无需点开任何抽屉 -->
    <div v-else class="view-body">
      <div class="name-line">
        <span class="brief-name">{{ brief.title || '（未填游戏名）' }}</span>
        <span v-if="brief.subtitle" class="muted sub">{{ brief.subtitle }}</span>
      </div>

      <div v-if="briefEmpty" class="brief-empty">
        还没填写项目设定。填上游戏名、简介、<strong>关键词</strong>与<strong>美术风格</strong>后，
        AI 生底板 / 生成配图 / 生成文案会统一使用这套语料，风格更一致。
      </div>
      <template v-else>
        <p v-if="brief.oneLiner" class="brief-line">「{{ brief.oneLiner }}」</p>

        <div v-if="brief.players || brief.playTime || brief.age" class="brief-kv">
          <span v-if="brief.players"><b>人数</b> {{ brief.players }}</span>
          <span v-if="brief.playTime"><b>时长</b> {{ brief.playTime }}</span>
          <span v-if="brief.age"><b>适龄</b> {{ brief.age }}</span>
        </div>

        <div v-if="brief.genre?.length" class="brief-tags">
          <el-tag v-for="g in brief.genre" :key="g" size="small" effect="plain">{{ g }}</el-tag>
        </div>

        <div v-if="brief.synopsis" class="brief-sec">
          <div class="brief-sec-t">简介</div>
          <p class="brief-text">{{ brief.synopsis }}</p>
        </div>

        <div v-if="brief.keywords?.length" class="brief-sec">
          <div class="brief-sec-t">关键词</div>
          <div class="brief-tags">
            <el-tag v-for="k in brief.keywords" :key="k" size="small">{{ k }}</el-tag>
          </div>
        </div>

        <div v-if="hasArt" class="brief-sec">
          <div class="brief-sec-t">美术</div>
          <div v-if="brief.artStyle?.style" class="brief-art-style">{{ brief.artStyle.style }}</div>
          <div v-if="palette.length" class="swatches">
            <i v-for="c in palette" :key="c" :style="{ background: c }" :title="c"></i>
            <span class="muted small">{{ palette.join(' ') }}</span>
          </div>
          <div v-if="brief.artStyle?.mood?.length" class="brief-text small">
            氛围：{{ brief.artStyle.mood.join(' · ') }}
          </div>
          <div v-if="brief.artStyle?.references?.length" class="brief-text small">
            参考：{{ brief.artStyle.references.join('、') }}
          </div>
          <div v-if="brief.artStyle?.details" class="brief-text small">
            {{ brief.artStyle.details }}
          </div>
        </div>

        <div v-if="brief.factions?.length" class="brief-sec">
          <div class="brief-sec-t">派系</div>
          <div class="brief-factions">
            <div v-for="f in brief.factions" :key="f.name" class="faction">
              <i :style="{ background: f.color }"></i>
              <span class="faction-name">{{ f.name }}</span>
              <span v-if="f.desc" class="muted small">{{ f.desc }}</span>
            </div>
          </div>
        </div>

        <div v-if="brief.taboos?.length" class="brief-sec">
          <div class="brief-sec-t">禁忌</div>
          <div class="brief-tags">
            <el-tag v-for="t in brief.taboos" :key="t" size="small"
                    type="danger" effect="plain">{{ t }}</el-tag>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * 项目设定（创作简报，§4.4 / §6.11）。
 *
 * 这是一个**常驻面板**：直接铺在项目概览页左栏，查看态把设定全文摊开显示，
 * 点「编辑」在同一块区域换成表单，改完点「保存」回查看态。
 * （原先用抽屉 el-drawer，用户反馈"必须点进去才看得到"，故改为内联。）
 */
import { computed, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '../api/client'
import { useUnsavedGuard } from '../composables/useUnsavedGuard'
import {
  AGE_OPTIONS, ART_STYLES, GENRES, MOODS, PALETTE_PRESETS, PLAYER_OPTIONS,
  TABOOS, TIME_OPTIONS, emptyBrief, extractKeywords, isBriefEmpty, normalizeBrief
} from '../constants/brief'

const props = defineProps<{ pid: string; brief?: any }>()
const emit = defineEmits<{ (e: 'saved', brief: any): void }>()

const editing = ref(false)
const b = ref<any>(emptyBrief())
const open = ref<string[]>(['basic', 'world', 'art'])
const saving = ref(false)
const keywordPool = ref<string[]>([])
const savedAt = ref('')

// 查看态取父级最新数据；编辑态不覆盖用户正在改的内容
watch(() => props.brief, (v) => {
  if (v === undefined) return
  if (!editing.value) b.value = normalizeBrief(v)
  // 空简报直接进编辑态：否则左栏只有一段引导文字，什么都看不着
  if (isBriefEmpty(v)) editing.value = true
}, { immediate: true })

const brief = computed(() => ({ ...emptyBrief(), ...(props.brief || {}) }))
const briefEmpty = computed(() => isBriefEmpty(props.brief))
const palette = computed(() => (brief.value.artStyle?.palette || []).filter(Boolean))
const hasArt = computed(() =>
  !!(brief.value.artStyle?.style || palette.value.length
     || brief.value.artStyle?.mood?.length || brief.value.artStyle?.references?.length
     || brief.value.artStyle?.details))

const payload = computed(() => {
  const c: any = JSON.parse(JSON.stringify(b.value))
  c.artStyle.palette = c.artStyle.palette.filter(Boolean)
  return c
})

function startEdit() {
  b.value = normalizeBrief(props.brief)
  keywordPool.value = extractKeywords([b.value.oneLiner, b.value.synopsis], b.value.keywords, 8)
  editing.value = true
}

function cancel() {
  editing.value = false
}

/**
 * 面板是常驻的（不是弹窗），用户很容易编到一半直接点「返回首页」——
 * 未保存的编辑内容要拦一下。只在"正在编辑且表单与服务器数据不一致"时算脏。
 */
const dirty = () => editing.value &&
  JSON.stringify(b.value) !== JSON.stringify(normalizeBrief(props.brief))
useUnsavedGuard(dirty, () => save(true))

async function save(explicit: boolean, force = false) {
  saving.value = true
  try {
    const r = await api.put(
      `/projects/${props.pid}/brief${force ? '?force=true' : ''}`, payload.value)
    savedAt.value = new Date().toLocaleTimeString()
    emit('saved', r.brief)
    editing.value = false
    if (explicit) ElMessage.success('项目设定已保存')
  } catch (e: any) {
    const msg = e?.message || '保存失败'
    // 后端有"防误清空"闸：把非空设定提交成全空时返回 409，这里再确认一次
    if (msg.includes('清空')) {
      const ok = await ElMessageBox
        .confirm(msg, '确认清空项目设定？', { type: 'warning', confirmButtonText: '确认清空' })
        .then(() => true).catch(() => false)
      if (ok) {
        saving.value = false
        return save(explicit, true)
      }
    } else {
      ElMessage.error(msg)
    }
  } finally { saving.value = false }
}

function addFaction() {
  b.value.factions.push({ name: '', desc: '', color: '#8a8f98' })
}

function applyPreset(name: string) {
  const p = PALETTE_PRESETS.find(x => x.name === name)
  if (p) b.value.artStyle.palette = [...p.colors]
}

function pickKeywords() {
  const got = extractKeywords([b.value.oneLiner, b.value.synopsis], b.value.keywords, 8)
  if (!got.length) return ElMessage.info('没能从文字里提取到新候选词，直接手动输入即可')
  b.value.keywords = [...(b.value.keywords || []), ...got]
  ElMessage.success(`已补充 ${got.length} 个候选关键词，可自行删改`)
}
</script>

<style scoped>
.head { margin-bottom: 4px; }
.head .title { font-size: 15px; font-weight: 700; }
.head .sub { font-size: 12px; }
.tip {
  background: #f5f7fa; border-radius: 6px; padding: 8px 10px;
  font-size: 12px; line-height: 1.6; color: var(--muted); margin: 10px 0 6px;
}
.edit-body { padding-bottom: 4px; }
.edit-body :deep(.el-collapse) { border-top: none; }
.edit-body .sec { font-weight: 600; }
.kw { width: 100%; }
.kw :deep(.el-button) { margin-top: 4px; }
.factions { width: 100%; }
.faction-row { display: flex; align-items: center; gap: 6px; margin-bottom: 6px; }
.palette { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.swatches { display: inline-flex; align-items: center; gap: 4px; flex-wrap: wrap; }
.swatches i {
  width: 16px; height: 16px; border-radius: 4px; display: inline-block;
  border: 1px solid rgba(0, 0, 0, .12);
}
.foot { margin-top: 12px; }
.foot .muted { font-size: 12px; }

/* ---- 查看态 ---- */
.view-body { padding-top: 8px; }
.name-line { display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap; }
.brief-name { font-size: 16px; font-weight: 700; }
.brief-empty { font-size: 12px; line-height: 1.7; color: var(--muted); padding: 10px 0 0; }
.brief-line { margin: 10px 0 8px; font-size: 13px; color: #444; line-height: 1.6; }
.brief-kv {
  display: flex; flex-wrap: wrap; gap: 4px 14px;
  font-size: 12px; color: var(--text); margin-bottom: 8px;
}
.brief-kv b { font-weight: 500; color: var(--muted); margin-right: 4px; }
.brief-tags { display: flex; gap: 6px; flex-wrap: wrap; }
.brief-sec { margin-top: 12px; padding-top: 10px; border-top: 1px dashed var(--border); }
.brief-sec-t { font-size: 12px; font-weight: 600; color: var(--muted); margin-bottom: 6px; }
.brief-text { margin: 0; font-size: 13px; line-height: 1.7; color: #444; white-space: pre-wrap; }
.brief-art-style { font-size: 13px; font-weight: 600; margin-bottom: 6px; }
.small { font-size: 11px; }
.swatches .small { margin-left: 4px; }
.brief-factions { display: flex; flex-direction: column; gap: 5px; }
.brief-factions .faction { display: flex; align-items: center; gap: 6px; font-size: 12px; }
.brief-factions .faction i {
  width: 10px; height: 10px; border-radius: 50%; display: inline-block; flex: none;
}
.brief-factions .faction-name { font-weight: 600; flex: none; }
</style>
