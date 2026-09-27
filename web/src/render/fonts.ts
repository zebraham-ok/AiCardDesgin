/**
 * 字体体系：本机字体优先，自定义字体按需入库（G2 + G10）。
 *
 * 设计原则（用户 2026-09-27 定调）：
 *   **asset 里只存"用户主动上传的自定义字体"，绝大多数用字直接引用本机已装字体。**
 *
 *   来源一 · 内置族（sans-serif / serif / monospace）—— 零成本，永远可用；
 *   来源二 · 本机字体 —— 不复制文件，模板里直接写族名，浏览器用系统已装字体渲染。
 *           扫描两条通道：
 *             a) `window.queryLocalFonts()`（Chrome/Edge 103+，localhost 属安全上下文，
 *                需用户手势触发授权）—— 全量枚举；
 *             b) `FontFace(..., 'local("X")')` 逐个探测预置候选族名 —— 所有浏览器可用、
 *                零权限，用于 Firefox/Safari 或用户拒绝授权时的兜底。
 *           扫描结果缓存进 localStorage，避免每次进页面都弹权限。
 *   来源三 · 自定义字体 asset —— `bgw_<assetId>`，按需下载 + `FontFace` 注册，
 *           可随项目包迁移，跨机不依赖对方装没装同款字体。
 *
 * 字号提示：自定义字体动辄 10MB+，所以清单与文件分离、用到才下载。
 */
import { api, assetUrl } from '../api/client'

// ---------------------------------------------------------------------------
// 类型
// ---------------------------------------------------------------------------
export interface FontAsset {
  id: string
  name: string
  ext?: string
  size?: number
}

export type FontSource = 'builtin' | 'local' | 'asset'

export interface FontChoice {
  label: string
  family: string
  source: FontSource
  /** asset 字体：文件是否已成功注册到 document.fonts */
  loaded?: boolean
  /** asset 字体：注册失败原因 */
  error?: string
  /** 搜索用的额外关键词（本机字体的 fullName/style 等，见 fontAliases.ts 的 matchFont） */
  keywords?: string[]
}

export interface LocalFont {
  family: string
  /** scan = queryLocalFonts 枚举到的；probe = local() 探测命中的候选 */
  from: 'scan' | 'probe'
  fullName?: string
  style?: string
}

export interface ScanResult {
  fonts: LocalFont[]
  mode: 'scan' | 'probe' | 'none'
  /** 走兜底或彻底失败时的原因，用于 UI 提示 */
  error?: string
}

// ---------------------------------------------------------------------------
// 常量
// ---------------------------------------------------------------------------
/** 内置系统族（永远可用，无需注册） */
export const BUILTIN_FONTS: FontChoice[] = [
  { label: '默认黑体（系统）', family: 'sans-serif', source: 'builtin' },
  { label: '衬线宋体（系统）', family: 'serif', source: 'builtin' },
  { label: '等宽（系统）', family: 'monospace', source: 'builtin' }
]

/**
 * 探测用候选清单：`queryLocalFonts()` 不可用时（Firefox/Safari、拒绝授权），
 * 用 `local()` 逐个试这些常见族名，命中的就算"检测到的本机字体"。
 * 覆盖 Windows / macOS / Linux 常见中英文字体。
 */
export const CANDIDATE_LOCAL_FONTS = [
  // 中文 · Windows
  'Microsoft YaHei', '微软雅黑', 'Microsoft YaHei UI', 'SimHei', '黑体', 'SimSun', '宋体',
  'NSimSun', '新宋体', 'KaiTi', '楷体', 'FangSong', '仿宋', 'DengXian', '等线',
  'Microsoft JhengHei', 'MingLiU', 'PMingLiU',
  // 中文 · macOS
  'PingFang SC', 'PingFang TC', 'Hiragino Sans GB', 'STHeiti', 'STSong', 'STKaiti',
  'STFangsong', 'Songti SC', 'Heiti SC',
  // 中文 · 开源 / Linux
  'Source Han Sans SC', 'Source Han Serif SC', 'Noto Sans CJK SC', 'Noto Serif CJK SC',
  'WenQuanYi Micro Hei', 'WenQuanYi Zen Hei',
  // 西文
  'Arial', 'Helvetica', 'Times New Roman', 'Georgia', 'Verdana', 'Tahoma',
  'Trebuchet MS', 'Impact', 'Courier New', 'Consolas', 'Calibri', 'Cambria',
  'Segoe UI', 'Palatino', 'Garamond', 'Futura', 'Optima', 'Roboto', 'Noto Sans'
]

const LOCAL_CACHE_KEY = 'bgw.localFonts.v1'

// ---------------------------------------------------------------------------
// 自定义字体 asset（来源三）
// ---------------------------------------------------------------------------
/**
 * 自定义字体在模板 schema 的 `style.fontFamily` 里存的名字。
 * 用 asset id 派生而不是用文件名：稳定、唯一、不怕重名，删掉重传也不会串。
 */
export const familyOf = (a: FontAsset) => `bgw_${String(a.id).replace(/^as_/, '')}`

/** 反解：`bgw_<id>` → asset id（`server/api/exports.py` 打包资源时要按同样的规则找回来） */
export const assetIdOfFamily = (family?: string) =>
  family && family.startsWith('bgw_') ? `as_${family.slice(4).replace(/^as_/, '')}` : null

/** 是否为自定义字体 asset 的 family（其余一律当作系统/本机族名，交给浏览器即可） */
export const isCustomFamily = (family?: string) =>
  !!family && family.startsWith('bgw_')

let list: FontAsset[] = []
const registered = new Set<string>()
const failed = new Map<string, string>()
const pending = new Map<string, Promise<boolean>>()

export const fontAssets = () => list

export function isFontRegistered(family: string) {
  return BUILTIN_FONTS.some(b => b.family === family) || registered.has(family)
}

export function fontError(family: string) {
  return failed.get(family)
}

/** 拉取自定义字体清单（默认有缓存；force=true 用于上传/删除后刷新） */
export async function refreshFontList(force = false): Promise<FontAsset[]> {
  if (list.length && !force) return list
  try {
    const r = await api.get<FontAsset[]>('/assets?type=font')
    list = Array.isArray(r) ? r : []
  } catch {
    if (force) list = []      // 后端不可用时至少不要让下拉崩掉
  }
  return list
}

async function register(a: FontAsset): Promise<boolean> {
  const family = familyOf(a)
  if (registered.has(family)) return true
  const inflight = pending.get(family)
  if (inflight) return inflight

  const task = (async () => {
    try {
      if (typeof FontFace === 'undefined') throw new Error('当前环境不支持 FontFace')
      const face = new FontFace(family, `url("${assetUrl(a.id)}")`)
      await face.load()
      ;(document as any).fonts?.add(face)
      // 等一次 fonts.ready，避免刚注册完立刻渲染时量出来的文本框宽度还是旧字体
      await (document as any).fonts?.ready
      registered.add(family)
      failed.delete(family)
      return true
    } catch (e: any) {
      failed.set(family, e?.message || '字体加载失败')
      return false
    } finally {
      pending.delete(family)
    }
  })()
  pending.set(family, task)
  return task
}

/**
 * 按需确保某个 family 可用。
 * 内置族/本机族名直接返回 true（浏览器自己会用系统字体渲染，无需注册）；
 * 未知的 `bgw_` 家族才去下载注册。
 */
export async function ensureFamily(family?: string): Promise<boolean> {
  if (!family) return true
  if (!isCustomFamily(family)) return true
  await refreshFontList()
  const a = list.find(x => familyOf(x) === family)
  if (!a) return false
  return register(a)
}

/** 把模板里用到的自定义字体一次注册齐（字段 + 图层文本样式都扫） */
export async function ensureFamiliesIn(tpl: any): Promise<void> {
  const fams = new Set<string>()
  const scan = (s: any) => { if (isCustomFamily(s?.fontFamily)) fams.add(s.fontFamily) }
  for (const f of tpl?.fields ?? []) scan(f.style)
  for (const l of tpl?.layers ?? []) scan(l.style)
  if (!fams.size) return
  await refreshFontList()
  await Promise.all([...fams].map(f => ensureFamily(f)))
}

/** 上传一个字体文件成为自定义 asset，返回新建的 asset */
export async function uploadFont(file: File): Promise<FontAsset> {
  const form = new FormData()
  form.append('file', file)
  form.append('type', 'font')
  form.append('name', file.name.replace(/\.[^.]+$/, ''))
  const a = await api.upload<FontAsset>('/assets/upload', form)
  await refreshFontList(true)
  await register(a)
  return a
}

// ---------------------------------------------------------------------------
// 本机字体（来源二）
// ---------------------------------------------------------------------------
export const canEnumerateLocalFonts = () =>
  typeof (window as any)?.queryLocalFonts === 'function'

function readCache(): LocalFont[] {
  try {
    const raw = localStorage.getItem(LOCAL_CACHE_KEY)
    const arr = raw ? JSON.parse(raw) : []
    return Array.isArray(arr) ? arr : []
  } catch { return [] }
}

let locals: LocalFont[] = readCache()
let scannedAt: number | null = locals.length ? Date.now() : null

/** 已扫描到的本机字体（含上一次的结果，来自缓存） */
export const localFonts = () => locals
export const hasScannedLocalFonts = () => scannedAt !== null

/** `local("X")` 能 load 成功即说明本机装了该族 */
async function localFamilyExists(family: string): Promise<boolean> {
  try {
    if (typeof FontFace === 'undefined') return false
    const probe = new FontFace('__bgw_probe__',
      `local("${family.replace(/["\\]/g, '')}")`)
    await probe.load()
    return true
  } catch { return false }
}

/** 兜底：逐个探测预置候选族名（零权限，所有浏览器可用） */
async function probeCandidates(): Promise<LocalFont[]> {
  const hits = await Promise.all(
    CANDIDATE_LOCAL_FONTS.map(async family =>
      (await localFamilyExists(family)) ? { family, from: 'probe' as const } : null))
  return hits.filter(Boolean) as LocalFont[]
}

function cache(list2: LocalFont[]) {
  locals = list2
  scannedAt = Date.now()
  try { localStorage.setItem(LOCAL_CACHE_KEY, JSON.stringify(list2)) } catch { /* 隐私模式忽略 */ }
}

/**
 * 扫描本机字体。必须在**用户手势**里调用（权限框需要 transient activation）。
 * 主通道 queryLocalFonts；不可用或被拒 → 退回 local() 探测候选清单。
 */
export async function scanLocalFonts(): Promise<ScanResult> {
  const qlf = (window as any)?.queryLocalFonts
  if (typeof qlf === 'function') {
    try {
      const found: any[] = await qlf.call(window)
      const map = new Map<string, LocalFont>()
      for (const f of found || []) {
        const family = String(f?.family || '').trim()
        if (!family || map.has(family)) continue
        map.set(family, { family, from: 'scan', fullName: f.fullName, style: f.style })
      }
      const out = [...map.values()].sort((a, b) => a.family.localeCompare(b.family))
      cache(out)
      return { fonts: out, mode: 'scan' }
    } catch (e: any) {
      // NotAllowedError = 用户拒绝授权；其他按失败处理，统一走探测兜底
      const reason = e?.name === 'NotAllowedError'
        ? '未获得本机字体访问授权'
        : (e?.message || '本机字体枚举失败')
      const probed = await probeCandidates()
      cache(probed)
      return { fonts: probed, mode: 'probe', error: `${reason}，已改为按常见字体名探测` }
    }
  }

  const probed = await probeCandidates()
  cache(probed)
  return {
    fonts: probed, mode: 'probe',
    error: '当前浏览器不支持自动枚举本机字体（Chrome/Edge 103+ 支持），已按常见字体名探测'
  }
}

/** 不触发权限的"轻刷新"：只读缓存 */
export function loadCachedLocalFonts(): LocalFont[] {
  locals = readCache()
  return locals
}

// ---------------------------------------------------------------------------
// 汇总选项
// ---------------------------------------------------------------------------
/** 字体下拉选项：内置 → 本机 → 自定义 asset（三来源分组用 source 区分） */
export function fontChoices(): FontChoice[] {
  return [
    ...BUILTIN_FONTS,
    ...locals
      .slice()
      .sort((a, b) => a.family.localeCompare(b.family))
      .map(l => ({
        label: l.family,
        family: l.family,
        source: 'local' as const,
        // 本机字体的 fullName（如 "Microsoft YaHei Bold"）也参与搜索
        keywords: [l.fullName, l.style].filter(Boolean) as string[]
      })),
    ...list.map(a => ({
      label: a.name,
      family: familyOf(a),
      source: 'asset' as const,
      loaded: registered.has(familyOf(a)),
      error: failed.get(familyOf(a)),
      keywords: [a.id]
    }))
  ]
}

/** 预热清单（不下载字体文件），供应用启动时调用 */
export async function warmupFonts() {
  await refreshFontList()
}
