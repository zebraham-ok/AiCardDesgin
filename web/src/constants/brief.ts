/**
 * 创作简报（ProjectBrief）的预设选项与工具（§4.4 / §P1）。
 *
 * 这里只放**前端 UI 用的常量与本地小工具**；语料的实际拼装在后端
 * `server/ai/prompt.py`（§6.11），避免两边各写一套规则。
 */

export const ART_STYLES = [
  '厚涂数字绘画', '日式动画赛璐璐', '欧美漫画', '像素风', '水墨国风', '蒸汽朋克',
  '水彩绘本', '复古铜版画', '手工剪纸', '低多边形 3D', '赛博霓虹', '极简线稿'
]

export const MOODS = [
  '史诗', '冷峻', '神秘', '温馨', '幽默', '黑暗', '明快', '治愈', '紧张', '荒诞', '苍凉', '华丽'
]

export const GENRES = [
  '卡牌对战', '卡牌构筑', '工人放置', '版图策略', '合作战役', '派对游戏',
  '推理', '跑团辅助', '儿童', '教育', '资源管理', '区域控制'
]

export const TABOOS = [
  '不要文字', '不要人物', '不要现代元素', '不要恐怖元素', '不要霓虹高饱和', '不要水印签名'
]

export const PLAYER_OPTIONS = ['1 人', '1-2 人', '2 人', '2-4 人', '3-6 人', '4-8 人', '6 人以上']
export const TIME_OPTIONS = ['15-30 分钟', '30-60 分钟', '60-120 分钟', '120 分钟以上']
export const AGE_OPTIONS = ['6+', '8+', '10+', '12+', '14+', '18+']

/** 常用主色板起手式（用户可改） */
export const PALETTE_PRESETS: { name: string; colors: string[] }[] = [
  { name: '暗金奇幻', colors: ['#1b1410', '#3d2a18', '#c9a227', '#e8e3d6'] },
  { name: '冷峻科幻', colors: ['#0b1a2b', '#12314f', '#5aa9e6', '#e2e8f0'] },
  { name: '水墨国风', colors: ['#f5f2ea', '#2b2b2b', '#7a8b7f', '#b34a3a'] },
  { name: '霓虹赛博', colors: ['#0a0a12', '#2b0f4a', '#ff2e88', '#22e0d6'] },
  { name: '温暖绘本', colors: ['#fdf3e3', '#f2b880', '#8ab07a', '#4a5d6e'] },
  { name: '废土荒漠', colors: ['#3a2f26', '#7c5c3b', '#c2a04a', '#8f9aa3'] }
]

/** 空简报（新建项目 / 老项目没有 brief 时的初值） */
export function emptyBrief() {
  return {
    title: '', subtitle: '', oneLiner: '', synopsis: '',
    players: '', playTime: '', age: '',
    genre: [], keywords: [], taboos: [],
    artStyle: { style: '', palette: [], mood: [], references: [], details: '' },
    factions: [] as any[]
  }
}

/** 后端返回的 brief 补全成完整结构（缺字段时用默认值兜住，避免表单 v-model 报错） */
export function normalizeBrief(raw: any) {
  const b = emptyBrief()
  if (!raw) return b
  const as = raw.artStyle || {}
  return {
    ...b, ...raw,
    genre: raw.genre || [], keywords: raw.keywords || [], taboos: raw.taboos || [],
    factions: (raw.factions || []).map((f: any) => ({
      name: f?.name || '', desc: f?.desc || '', color: f?.color || '#8a8f98'
    })),
    artStyle: {
      ...b.artStyle, ...as,
      palette: as.palette || [], mood: as.mood || [], references: as.references || []
    }
  }
}

/** 简报是否还是空壳（用于概览页显示引导） */
export function isBriefEmpty(b: any) {
  if (!b) return true
  return !(b.oneLiner || b.synopsis || b.keywords?.length || b.artStyle?.style)
}

// ---------------------------------------------------------------------------
// 关键词提取（本地，不调 AI）
// ---------------------------------------------------------------------------
/** 题材高频词库：命中即优先入选，让候选词看起来"像游戏词" */
const VOCAB = [
  '星际', '太空', '舰队', '星域', '帝国', '遗迹', '黑洞', '虫洞', '殖民', '星图',
  '魔法', '法师', '精灵', '龙族', '亡灵', '符文', '炼金', '召唤', '诅咒', '神祇',
  '骑士', '王国', '城堡', '贵族', '佣兵', '刺客', '公会', '边境', '铁匠', '酒馆',
  '蒸汽', '机械', '齿轮', '工厂', '飞艇', '铁路', '火药', '殖民', '发明',
  '荒野', '废土', '幸存', '变异', '丧尸', '辐射', '拾荒', '母舰',
  '城邦', '文明', '贸易', '商队', '航线', '航海', '海盗', '港囗', '港口', '灯塔',
  '森林', '沙漠', '冰原', '火山', '深海', '高原', '沼泽', '洞窟', '秘境',
  '资源', '矿石', '木材', '粮食', '水晶', '能量', '金币', '契约', '声望', '影响力',
  '战争', '对抗', '联盟', '背叛', '阴谋', '探索', '生存', '建造', '经营', '竞速'
]

const STOP = new Set(['的', '了', '和', '与', '及', '在', '是', '为', 'with', 'the', 'and', '一个', '这个', '可以', '进行', '通过', '以及', '我们', '他们'])

/**
 * 从「一句话卖点 + 简介」里提取关键词候选。
 * 纯本地启发式：词库命中优先 → 再补 2-6 字的中文片段 → 去重截断。
 * 只作为**下拉的候选**，用户可随意删改，所以宁多勿少。
 */
export function extractKeywords(texts: string[], exists: string[] = [], limit = 8): string[] {
  const text = texts.filter(Boolean).join(' ')
  if (!text.trim()) return []
  const found: { word: string; score: number }[] = []
  const seen = new Set<string>()

  for (const w of VOCAB) {
    if (text.includes(w) && !exists.includes(w) && !seen.has(w)) {
      seen.add(w)
      found.push({ word: w, score: 3 })
    }
  }
  // 中文连贯片段 / 英文单词 / 数字连写
  for (const m of text.match(/[\u4e00-\u9fa5]{2,6}|[A-Za-z][A-Za-z0-9\-]{2,20}/g) || []) {
    const w = m.trim()
    if (w.length < 2 || STOP.has(w) || exists.includes(w) || seen.has(w)) continue
    seen.add(w)
    found.push({ word: w, score: 1 })
  }
  return found
    .sort((a, b) => b.score - a.score || a.word.length - b.word.length)
    .slice(0, limit)
    .map(f => f.word)
}
