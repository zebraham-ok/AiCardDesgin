/**
 * 常见字体的中英文别名表 —— 让字体下拉「搜中文能搜到英文族名，反之亦然」。
 *
 * 键 = 字体族名（浏览器/字体文件里的正式名，也是模板 `style.fontFamily` 里存的值），
 * 值 = 其它叫法：中文译名、正体字写法、旧名、PostScript 名等。
 *
 * 匹配是双向的：搜「微软雅黑」能命中 Microsoft YaHei，搜「YaHei」同样命中它。
 * 自定义字体（`bgw_<id>`）与用户手输的任意族名不受此表限制，仍走普通包含匹配。
 */

export const FONT_ALIASES: Record<string, string[]> = {
  // ---- 内置通用族 ----
  'sans-serif': ['无衬线', '黑体', '默认黑体', 'sans', '无衬线体'],
  serif: ['衬线', '宋体', '默认宋体', '有衬线', '衬线体'],
  monospace: ['等宽', '等距', '代码字体', 'mono', '等宽字体'],

  // ---- 中文 · Windows ----
  SimSun: ['宋体', '中易宋体', '新宋体', 'Sun', 'Simsun'],
  NSimSun: ['新宋体', '中易新宋体'],
  SimHei: ['黑体', '中易黑体', 'Simhei'],
  'Microsoft YaHei': ['微软雅黑', '雅黑', 'MS YaHei', 'MSYH', 'MicrosoftYaHei'],
  'Microsoft YaHei UI': ['微软雅黑 UI', '雅黑 UI'],
  KaiTi: ['楷体', '中易楷体', '楷体_GB2312', 'KaiTi_GB2312'],
  FangSong: ['仿宋', '中易仿宋', '仿宋_GB2312', 'FangSong_GB2312'],
  DengXian: ['等线', '等线体'],
  MingLiU: ['细明体', '細明體'],
  PMingLiU: ['新细明体', '新細明體'],
  'Microsoft JhengHei': ['微软正黑体', '微軟正黑體', '正黑体', 'JhengHei'],
  LiSu: ['隶书'],
  YouYuan: ['幼圆'],
  'SimSun-ExtB': ['宋体 ExtB'],
  '方正书宋': ['FZShuSong'],

  // ---- 中文 · macOS ----
  'PingFang SC': ['苹方', '苹方-简', '苹果苹方', 'PingFang', '平方'],
  'PingFang TC': ['苹方-繁', '蘋方'],
  'PingFang HK': ['苹方-港'],
  'Hiragino Sans GB': ['冬青黑体', '冬青黑體', 'Hiragino'],
  STHeiti: ['华文黑体', '華文黑體'],
  STSong: ['华文宋体', '華文宋體'],
  STKaiti: ['华文楷体', '華文楷體'],
  STFangsong: ['华文仿宋', '華文仿宋'],
  'Songti SC': ['宋体-简', '宋體-簡'],
  'Heiti SC': ['黑体-简', '黑體-簡'],
  'Kaiti SC': ['楷体-简', '楷體-簡'],
  'Lantinghei SC': ['兰亭黑', '蘭亭黑'],
  'Yuanti SC': ['圆体-简', '圓體-簡'],

  // ---- 中文 · 开源 / Linux ----
  'Source Han Sans SC': ['思源黑体', '思源黑體', '思源黑体简体', 'SourceHanSans'],
  'Source Han Serif SC': ['思源宋体', '思源宋體', 'SourceHanSerif'],
  'Noto Sans CJK SC': ['思源黑体', 'Noto 黑体', 'NotoSansCJK'],
  'Noto Serif CJK SC': ['思源宋体', 'Noto 宋体', 'NotoSerifCJK'],
  'Noto Sans SC': ['Noto 黑体', '思源黑体'],
  'Noto Serif SC': ['Noto 宋体', '思源宋体'],
  'WenQuanYi Micro Hei': ['文泉驿微米黑', '微米黑', '文泉驿'],
  'WenQuanYi Zen Hei': ['文泉驿正黑', '正黑'],
  'ZCOOL KuaiLe': ['站酷快乐体'],
  'Source Han Sans': ['思源黑体'],

  // ---- 西文（常见中文叫法）----
  Arial: ['阿里尔', 'Arial 黑体'],
  Helvetica: ['海尔维梯卡', '赫尔维提卡'],
  'Times New Roman': ['新罗马', '泰晤士新罗马', 'Times'],
  Georgia: ['乔治亚'],
  Verdana: ['韦尔达纳'],
  Tahoma: ['塔荷马'],
  Impact: ['冲击体', '因帕克特'],
  'Courier New': ['信使', '等宽信使'],
  Consolas: ['等宽代码', 'Consola'],
  Calibri: ['卡利布里'],
  Cambria: ['坎布里亚'],
  'Segoe UI': ['微软雅黑 UI 体', 'Segoe'],
  'Comic Sans MS': ['漫画体', '漫画'],
  'Trebuchet MS': ['特雷布切特'],
  Roboto: ['机器人'],
  Futura: ['未来体'],
  Optima: ['奥普蒂玛'],
  'Palatino Linotype': ['帕拉蒂诺'],
  Garamond: ['加拉蒙'],
  'Franklin Gothic Medium': ['富兰克林哥特'],
  'Book Antiqua': ['古文书体']
}

/** 取某族名的全部别名（无则空数组） */
export function aliasesOf(family?: string): string[] {
  if (!family) return []
  return FONT_ALIASES[family] || []
}

export interface SearchableFont {
  family: string
  label?: string
  /** 额外可搜字段：本机字体的 fullName / style、自定义字体的原文件名等 */
  keywords?: string[]
}

/** 关键词是否命中该字体（族名 / 显示名 / 中英文别名 / 额外关键词，全部大小写不敏感） */
export function matchFont(f: SearchableFont, query: string): boolean {
  const q = (query || '').trim().toLowerCase()
  if (!q) return true
  const hay = [f.family, f.label || '', ...aliasesOf(f.family), ...(f.keywords || [])]
  return hay.some(s => !!s && String(s).toLowerCase().includes(q))
}

/** 匹配度排序：族名完全相等 > 前缀命中 > 其它（让最贴切的排前面） */
export function rankFont(f: SearchableFont, query: string): number {
  const q = (query || '').trim().toLowerCase()
  if (!q) return 0
  const fam = f.family.toLowerCase()
  if (fam === q) return 0
  if (fam.startsWith(q)) return 1
  if ((f.label || '').toLowerCase().startsWith(q)) return 2
  return 3
}
