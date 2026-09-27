/**
 * M3 渲染与导出引擎（§P5）。
 *
 * 设计要点：
 *  - **渲染全在浏览器**：走同一个 `renderTemplate`，所以导出与编辑器所见一致。
 *  - **两级模式**：trim（不含出血，净尺寸）/ bleed（含出血，四周各外扩 3mm）。
 *  - 离屏用 `StaticCanvas`（无交互开销），逐张释放，避免大批量爆内存。
 */
import { StaticCanvas } from 'fabric'
import JSZip from 'jszip'
import { jsPDF } from 'jspdf'
import { renderTemplate, contentSize } from './templateRenderer'

// ---------------------------------------------------------------------------
// 常量与工具
// ---------------------------------------------------------------------------
export const MM = 25.4
export const DPI_PRESETS = [150, 300, 600]
/** 出血量：模板 canvas.bleed 是设计像素，按基准 DPI 换算成 mm（默认 3mm） */
export const bleedMm = (tpl: any) =>
  (tpl?.canvas?.bleed ?? 0) / (tpl?.canvas?.dpi ?? 300) * MM

/** 3mm @300DPI = 36px；其它 DPI 按同一物理量换算 */
export const bleedPx = (dpi: number, baseDpi = 300) => Math.round(3 / MM * dpi)

export type BleedMode = 'trim' | 'bleed'
export type ImgFormat = 'png' | 'jpg'

export interface CardRenderOpts {
  /** 目标 DPI，缺省取模板 canvas.dpi */
  dpi?: number
  bleedMode?: BleedMode
}

/** 等待字体就绪（首次导出若字体未加载，文字会退回默认字形）。
 *  模板里引用的自定义字体由 renderTemplate → ensureFamiliesIn 按需注册。 */
export async function ensureFonts() {
  try {
    if (typeof document !== 'undefined' && (document as any).fonts?.ready) {
      await (document as any).fonts.ready
    }
  } catch { /* 忽略 */ }
}

const safeName = (s: string) =>
  String(s ?? '').replace(/[/\\:*?"<>|]/g, '_').trim() || 'card'

/**
 * 把一张卡渲染到离屏画布。返回的 StaticCanvas **由调用方负责 dispose()**。
 * 画布尺寸已是目标 DPI 下的最终像素尺寸（含出血则外扩）。
 */
export async function renderCardOffscreen(
  tpl: any, card: any, opts: CardRenderOpts = {}
): Promise<StaticCanvas> {
  const baseDpi = tpl?.canvas?.dpi ?? 300
  const dpi = opts.dpi ?? baseDpi
  const scale = dpi / baseDpi
  const bleed = opts.bleedMode === 'bleed'
  const size = contentSize(tpl, bleed)

  const el = document.createElement('canvas')
  el.width = Math.round(size.w * scale)
  el.height = Math.round(size.h * scale)
  const c = new StaticCanvas(el, {
    width: el.width, height: el.height,
    backgroundColor: '#ffffff', renderOnAddRemove: false
  })
  c.setZoom(scale)
  await renderTemplate(c, tpl, {
    card, interactive: false, bleedMode: bleed, guides: false
  })
  c.renderAll()
  return c
}

/** 画布 → dataURL。transparent 会把白色背景去掉（底板图层仍在） */
function canvasToDataUrl(c: StaticCanvas, format: ImgFormat, transparent = false) {
  if (transparent) {
    c.backgroundColor = 'rgba(0,0,0,0)'
    c.renderAll()
  }
  const el = c.getElement() as HTMLCanvasElement
  return el.toDataURL(
    format === 'png' ? 'image/png' : 'image/jpeg',
    format === 'png' ? undefined : 0.95
  )
}

function download(url: string, filename: string) {
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
}

/** 由模板生成文件名；支持 {{template}} / {{name}} / {{index}} */
export function fileName(
  tpl: any, card: any, pattern = '{{template}}_{{name}}', index = 0
) {
  const s = pattern
    .replace(/\{\{template\}\}/g, tpl?.name ?? 'card')
    .replace(/\{\{name\}\}/g, card?.name ?? 'card')
    .replace(/\{\{index\}\}/g, String(index + 1).padStart(2, '0'))
  return safeName(s)
}

// ---------------------------------------------------------------------------
// E1 单张导出
// ---------------------------------------------------------------------------
export interface SingleOpts extends CardRenderOpts {
  /** image = PNG/JPG；pdf = 单页 PDF */
  output: 'png' | 'jpg' | 'pdf'
  transparent?: boolean
  cutLines?: boolean
  filename?: string
}

export async function exportOne(tpl: any, card: any, opts: SingleOpts) {
  await ensureFonts()
  const bleed = opts.bleedMode === 'bleed'
  const dpi = opts.dpi ?? tpl?.canvas?.dpi ?? 300
  const base = opts.filename || fileName(tpl, card)
  const suffix = bleed ? '_bleed' : '_trim'
  const c = await renderCardOffscreen(tpl, card, { dpi, bleedMode: opts.bleedMode })

  if (opts.output === 'pdf') {
    const baseDpi = tpl?.canvas?.dpi ?? 300
    const size = contentSize(tpl, bleed)
    const wmm = size.w / baseDpi * MM
    const hmm = size.h / baseDpi * MM
    const pdf = new jsPDF({
      orientation: wmm > hmm ? 'landscape' : 'portrait',
      unit: 'mm', format: [wmm, hmm]
    })
    pdf.addImage(canvasToDataUrl(c, 'png'), 'PNG', 0, 0, wmm, hmm)
    if (bleed && opts.cutLines !== false) drawCutMarks(pdf, size, baseDpi, 0, 0)
    pdf.save(`${base}${suffix}.pdf`)
  } else {
    const fmt: ImgFormat = opts.output === 'png' ? 'png' : 'jpg'
    download(
      canvasToDataUrl(c, fmt, opts.transparent && opts.output === 'png'),
      `${base}${suffix}.${fmt === 'png' ? 'png' : 'jpg'}`
    )
  }
  c.dispose()
}

// ---------------------------------------------------------------------------
// E2-a 批量 ZIP
// ---------------------------------------------------------------------------
export interface ZipOpts extends CardRenderOpts {
  /** 文件名模板 */
  pattern?: string
  /** 附带数据清单 */
  withData?: boolean
  groupByTemplate?: boolean
}

export interface BatchProgress {
  done: number
  total: number
  label: string
  cancelled: boolean
}

export async function exportZip(
  templates: Record<string, any>,
  cards: any[],
  opts: ZipOpts,
  onProgress?: (p: BatchProgress) => void,
  shouldCancel?: () => boolean,
  zipName = 'cards'
) {
  await ensureFonts()
  const zip = new JSZip()
  const dpi = opts.dpi ?? 300
  const bleed = opts.bleedMode === 'bleed'
  const suffix = bleed ? '_bleed' : '_trim'
  const used = new Set<string>()
  const multiTpl = opts.groupByTemplate &&
    Object.keys(templates).length > 1
  const total = cards.length
  let done = 0

  for (let i = 0; i < cards.length; i++) {
    if (shouldCancel?.()) {
      onProgress?.({ done, total, label: '已中断', cancelled: true })
      return
    }
    const card = cards[i]
    const tpl = templates[card.templateId]
    if (!tpl) continue
    const c = await renderCardOffscreen(tpl, card, { dpi, bleedMode: opts.bleedMode })
    let name = fileName(tpl, card, opts.pattern, i) + suffix
    while (used.has(name)) name = `${name}_2`
    used.add(name)
    const dir = multiTpl ? `${safeName(tpl.name)}/` : ''
    zip.file(`${dir}${name}.png`,
      canvasToDataUrl(c, 'png').split(',')[1], { base64: true })
    c.dispose()
    done++
    onProgress?.({ done, total, label: card.name ?? '', cancelled: false })
    // 让出主线程，避免大批量时页面卡死
    await new Promise((r) => setTimeout(r, 0))
  }

  if (opts.withData) {
    zip.file('cards.json', JSON.stringify({ cards }, null, 2))
    zip.file('cards.csv', cardsToCsv(templates, cards))
  }

  const blob = await zip.generateAsync({ type: 'blob' })
  const url = URL.createObjectURL(blob)
  download(url, `${zipName}${suffix}.zip`)
  setTimeout(() => URL.revokeObjectURL(url), 4000)
  return { count: done, cancelled: false }
}

// ---------------------------------------------------------------------------
// E2-b PDF 拼版
// ---------------------------------------------------------------------------
export const PAPERS: Record<string, [number, number]> = {
  A4: [210, 297],
  A3: [297, 420],
  Letter: [215.9, 279.4]
}

export interface ImposeOpts extends CardRenderOpts {
  paper: string
  landscape?: boolean
  rows: number
  cols: number
  marginMm: number
  gapMm: number
  /** 含出血时相邻卡是否共享（重叠）出血区 */
  bleedShare?: 'shared' | 'independent'
  cutLines?: boolean
  backMode?: 'none' | 'mirror' | 'template'
  backTemplateId?: string
  pngName?: string
}

/** 在 (ox,oy) 处画一组裁切角线：四角向外延伸 2mm 的短线 */
function drawCutMarks(
  pdf: jsPDF, size: { offset: number; netW: number; netH: number },
  baseDpi: number, ox: number, oy: number
) {
  const b = size.offset / baseDpi * MM       // 出血宽度 mm
  const x = ox + b
  const y = oy + b
  const w = size.netW / baseDpi * MM
  const h = size.netH / baseDpi * MM
  const len = 2
  pdf.setLineWidth(0.1)
  pdf.setDrawColor(0, 0, 0)
  // 左上角
  pdf.lines([[0, len], [-len, 0]], x, y - len)
  pdf.lines([[len, 0], [0, len]], x - len, y)
  // 右上角
  pdf.lines([[0, len], [len, 0]], x + w, y - len)
  pdf.lines([[-len, 0], [0, len]], x + w + len, y)
  // 左下角
  pdf.lines([[0, -len], [-len, 0]], x, y + h + len)
  pdf.lines([[len, 0], [0, -len]], x - len, y + h)
  // 右下角
  pdf.lines([[0, -len], [len, 0]], x + w, y + h + len)
  pdf.lines([[-len, 0], [0, -len]], x + w + len, y + h)
}

export async function exportImposedPdf(
  templates: Record<string, any>,
  cards: any[],
  opts: ImposeOpts,
  onProgress?: (p: BatchProgress) => void,
  shouldCancel?: () => boolean
) {
  await ensureFonts()
  const tpl0 = templates[Object.keys(templates)[0]]
  const baseDpi = tpl0?.canvas?.dpi ?? 300
  const dpi = opts.dpi ?? baseDpi
  const netW = tpl0.canvas.w / baseDpi * MM
  const netH = tpl0.canvas.h / baseDpi * MM
  const bleed = opts.bleedMode === 'bleed'
  const B = bleed ? bleedMm(tpl0) : 0
  const imgW = netW + (bleed ? B * 2 : 0)
  const imgH = netH + (bleed ? B * 2 : 0)
  // 卡位间距（步长）：独立出血多占一份出血宽度
  const pitchX = bleed
    ? (opts.bleedShare === 'independent' ? netW + B * 2 : netW + B) + opts.gapMm
    : netW + opts.gapMm
  const pitchY = bleed
    ? (opts.bleedShare === 'independent' ? netH + B * 2 : netH + B) + opts.gapMm
    : netH + opts.gapMm

  const [pw0, ph0] = PAPERS[opts.paper] || PAPERS.A4
  const pageW = opts.landscape ? Math.max(pw0, ph0) : pw0
  const pageH = opts.landscape ? Math.min(pw0, ph0) : ph0

  let cols = opts.cols, rows = opts.rows
  const needW = (c: number) =>
    opts.marginMm * 2 + (c - 1) * pitchX + imgW
  const needH = (r: number) =>
    opts.marginMm * 2 + (r - 1) * pitchY + imgH
  // 放不下就提示（由调用方提前校验；这里做兜底裁剪，避免画到纸外）
  while (cols > 1 && needW(cols) > pageW) cols--
  while (rows > 1 && needH(rows) > pageH) rows--
  if (needW(cols) > pageW || needH(rows) > pageH) {
    throw new Error(`当前纸张放不下 ${cols}×${rows} 张卡，请减少行列或缩小出血间距`)
  }

  const per = cols * rows
  const backTpl = opts.backMode === 'template' && opts.backTemplateId
    ? templates[opts.backTemplateId] : null

  const total = cards.length +
    (opts.backMode && opts.backMode !== 'none' ? cards.length : 0)
  let done = 0

  const renderImg = async (card: any) => {
    const tpl = templates[card.templateId] || tpl0
    const c = await renderCardOffscreen(tpl, card, { dpi, bleedMode: opts.bleedMode })
    const url = canvasToDataUrl(c, 'png')
    c.dispose()
    done++
    onProgress?.({ done, total, label: card.name ?? '', cancelled: false })
    await new Promise((r) => setTimeout(r, 0))
    return url
  }

  const pdf = new jsPDF({ unit: 'mm', format: [pageW, pageH] })
  let firstPage = true
  let col = 0, row = 0

  const place = (url: string) => {
    const x = opts.marginMm + col * pitchX
    const y = opts.marginMm + row * pitchY
    pdf.addImage(url, 'PNG', x, y, imgW, imgH)
    if (bleed && opts.cutLines !== false) {
      const size = contentSize(tpl0, true)
      drawCutMarks(pdf, size, baseDpi, x, y)
    }
  }

  for (let i = 0; i < cards.length; i++) {
    if (shouldCancel?.()) {
      onProgress?.({ done, total, label: '已中断', cancelled: true })
      return
    }
    if (!firstPage) pdf.addPage([pageW, pageH])
    firstPage = false
    place(await renderImg(cards[i]))
  }

  // 背面：另起一轮页，同槽位镜像排布（双面逐页对齐）
  if (opts.backMode && opts.backMode !== 'none') {
    const frontCount = cards.length
    for (let p = 0; p < frontCount; p++) {
      if (shouldCancel?.()) {
        onProgress?.({ done, total, label: '已中断', cancelled: true })
        return
      }
      pdf.addPage([pageW, pageH])
      col = opts.backMode === 'mirror' ? (cols - 1 - (p % cols)) : (p % cols)
      row = Math.floor(p / cols) % rows
      const card = cards[p]
      const backCard = backTpl
        ? { ...card, templateId: opts.backTemplateId! } : card
      place(await renderImg(backCard))
    }
  }

  pdf.save(`${opts.pngName || 'cards'}${bleed ? '_bleed' : '_trim'}.pdf`)
  return { count: done, pages: pdf.getNumberOfPages(), cancelled: false }
}

/** 校验纸张能否放下 cols×rows（返回富余，负数表示放不下） */
export function imposeCheck(tpl: any, opts: ImposeOpts) {
  const baseDpi = tpl?.canvas?.dpi ?? 300
  const netW = tpl.canvas.w / baseDpi * MM
  const netH = tpl.canvas.h / baseDpi * MM
  const bleed = opts.bleedMode === 'bleed'
  const B = bleed ? bleedMm(tpl) : 0
  const imgW = netW + (bleed ? B * 2 : 0)
  const imgH = netH + (bleed ? B * 2 : 0)
  const share = bleed
    ? (opts.bleedShare === 'independent' ? B * 2 : B) : 0
  const pitchX = netW + share + opts.gapMm
  const pitchY = netH + share + opts.gapMm
  const [pw0, ph0] = PAPERS[opts.paper] || PAPERS.A4
  const pageW = opts.landscape ? Math.max(pw0, ph0) : pw0
  const pageH = opts.landscape ? Math.min(pw0, ph0) : ph0
  return {
    cw: pageW - opts.marginMm * 2 - ((opts.cols - 1) * pitchX + imgW),
    ch: pageH - opts.marginMm * 2 - ((opts.rows - 1) * pitchY + imgH)
  }
}

// ---------------------------------------------------------------------------
// E3 数据（Web 侧拼 CSV，与后端 export 保持一致）
// ---------------------------------------------------------------------------
export function cardsToCsv(templates: Record<string, any>, cards: any[]) {
  const keys: string[] = []
  for (const c of cards) {
    for (const k of Object.keys(c.fields ?? {})) {
      if (!keys.includes(k)) keys.push(k)
    }
  }
  const esc = (v: any) => {
    const s = v == null ? '' : String(v)
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
  }
  const rows = [['name', 'tags', ...keys].join(',')]
  for (const c of cards) {
    rows.push([esc(c.name), esc((c.tags || []).join('|')),
      ...keys.map((k) => esc(c.fields?.[k]))].join(','))
  }
  return rows.join('\n')
}
