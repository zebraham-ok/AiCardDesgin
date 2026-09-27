/**
 * 唯一的模板渲染引擎（Fabric.js）。
 *
 * 模板编辑器、卡牌编辑器、批量导出都走这里，保证「所见即所得」。
 * 所有坐标都是「设计像素」，与 template.canvas.w/h 同坐标系。
 */
import { StaticCanvas, Rect, Textbox, Group, FabricImage, Path } from 'fabric'
import { resolveAsset } from '../api/client'
import { ensureFamiliesIn } from './fonts'

export interface RenderOpts {
  /** 卡牌数据（fields 提供字段值）；不传则只渲染模板骨架 */
  card?: any
  /** 模板编辑模式：字段画成虚线框 + 标签，便于看清结构 */
  wireframe?: boolean
  /** 是否允许选中/拖动（导出时为 false） */
  interactive?: boolean
  /** 含出血模式：画布四周外扩 bleed，底板铺满出血区 */
  bleedMode?: boolean
  /** 是否绘制出血框 / 裁切框 / 安全框（编辑器用，导出时必须为 false） */
  guides?: boolean
  /**
   * 模板编辑模式：`guide: true` 的隐形定位框只在编辑器里显示（灰色虚线 + 名称），
   * 卡牌预览与导出完全不渲染 —— 它是给 AI 底板流程标记区域用的，不是可见内容。
   */
  editor?: boolean
}

/** 画布的物理尺寸与内容偏移（含出血模式会外扩） */
export function contentSize(tpl: any, bleedMode = false) {
  const W = tpl?.canvas?.w ?? 745
  const H = tpl?.canvas?.h ?? 1040
  const b = bleedMode ? (tpl?.canvas?.bleed ?? 0) : 0
  return { w: W + b * 2, h: H + b * 2, offset: b, netW: W, netH: H, bleed: b }
}

/** 安全边距：2mm（按 DPI 换算） */
export function safeMargin(tpl: any) {
  return Math.round((2 / 25.4) * (tpl?.canvas?.dpi ?? 300))
}

export const FIELD_COLORS: Record<string, string> = {
  text: '#4a90d9',
  textarea: '#4a90d9',
  number: '#d98a4a',
  enum: '#8a6fd9',
  image: '#4aa86a',
  icon: '#c2a04a'
}

export function fieldColor(kind: string) {
  return FIELD_COLORS[kind] || '#888'
}

/** 按 rect 把图片裁成 cover / contain，并支持圆角 */
async function makeImage(
  src: string, rect: number[], fit = 'cover', radius = 0, interactive = true
): Promise<any> {
  const [x, y, w, h] = rect
  const img = await FabricImage.fromURL(src, { crossOrigin: 'anonymous' })
  const iw = img.width || 1
  const ih = img.height || 1
  const scale = fit === 'cover'
    ? Math.max(w / iw, h / ih)
    : Math.min(w / iw, h / ih)
  img.set({
    left: x + w / 2,
    top: y + h / 2,
    originX: 'center',
    originY: 'center',
    scaleX: scale,
    scaleY: scale,
    selectable: interactive,
    evented: interactive
  })
  img.clipPath = new Rect({
    left: x, top: y, width: w, height: h,
    rx: radius, ry: radius, absolutePositioned: true
  })
  return img
}

/**
 * 背景底板绘制。
 *
 * 若模板记了 `background.bleedPx`（AI 底板按**含出血尺寸**生成，见 `server/ai/prompt.py`
 * 的 `baseplate_size`），且图片实际像素正好 = `净尺寸 + 2×bleedPx`，则**按像素 1:1 对齐**：
 *   * 含出血模式（画布已外扩，B = bleed）→ 图片放在 (0,0)，整张铺满；
 *   * 不含出血模式（画布 = 净尺寸，B = 0）→ 图片放在 (-bleed, -bleed)，
 *     画布恰好从图中间裁出净尺寸区域。
 * 两种模式都不缩放，所以编辑器所见 = 出图所得，贴边装饰不会被裁掉。
 *
 * 尺寸对不上（例如用户手动传了张别的图）就回退到 `cover` 铺满。
 */
async function makeBackground(tpl: any, src: string, CW: number, CH: number, B: number) {
  const b = Number(tpl?.background?.bleedPx || 0)
  const netW = Number(tpl?.canvas?.w ?? 745)
  const netH = Number(tpl?.canvas?.h ?? 1040)
  let img: any = null
  if (b > 0) {
    img = await FabricImage.fromURL(src, { crossOrigin: 'anonymous' })
    const okW = Math.abs((img.width || 0) - (netW + b * 2)) <= 2
    const okH = Math.abs((img.height || 0) - (netH + b * 2)) <= 2
    if (okW && okH) {
      img.set({
        left: B - b, top: B - b, originX: 'left', originY: 'top',
        scaleX: 1, scaleY: 1, selectable: false, evented: false
      })
      return applyMask(img, tpl, CW, CH, B)
    }
  }
  img = await makeImage(src, [0, 0, CW, CH], tpl?.background?.fit || 'cover', 0, false)
  return applyMask(img, tpl, CW, CH, B)
}

/**
 * 底板挖空：`background.mask` 是**净尺寸设计坐标**下的一组矩形 `[[x,y,w,h], …]`，
 * 这些地方不画底板（露出画布底色；PNG 导出勾"透明背景"时就是真透明）。
 *
 * 实现用「一条外框 + 若干内框」的 evenodd 路径当 clipPath（fabric 的 Path 会
 * `ctx.fill('evenodd')`），比在离屏 canvas 上做 `destination-out` 合成简单得多，
 * 而且**不产生新资源、可反复编辑、可撤销** —— 直接改图（烘焙成新 PNG）会带来
 * 一堆重复素材，还会污染全局共享的 assets 库。
 *
 * 坐标要加 B（含出血模式下画布整体偏移），与其它元素走同一套 `off()` 逻辑。
 */
function applyMask(img: any, tpl: any, CW: number, CH: number, B: number) {
  const mask: number[][] = Array.isArray(tpl?.background?.mask) ? tpl.background.mask : []
  if (!mask.length) return img
  const d = maskPathD(mask, CW, CH, B)
  if (!d) return img
  img.clipPath = new Path(d, {
    fill: '#000', fillRule: 'evenodd', absolutePositioned: true,
    selectable: false, evented: false
  })
  return img
}

/**
 * 底板在**净尺寸设计坐标**下的摆放（left/top/scale）。
 *
 * 抽出来是为了「挖空底板」对话框能显示出与导出**完全一致**的画面：
 * 两边各算一遍的话，差一点用户框的位置就和实际挖空的位置错开了。
 */
export function backgroundPlacement(iw: number, ih: number, netW: number, netH: number,
                                    bleedPx = 0) {
  const b = Number(bleedPx || 0)
  if (b > 0 && Math.abs(iw - (netW + b * 2)) <= 2 && Math.abs(ih - (netH + b * 2)) <= 2) {
    // 与渲染器的「像素 1:1 对齐」一致：净尺寸视图下从中间裁掉四周出血
    return { left: -b, top: -b, scale: 1 }
  }
  const scale = Math.max(netW / iw, netH / ih)         // cover
  return { left: (netW - iw * scale) / 2, top: (netH - ih * scale) / 2, scale }
}

/** 外框（整张画布）+ 内框（挖空区），evenodd 下内框变成洞 */
export function maskPathD(mask: number[][], CW: number, CH: number, B = 0) {
  const outer = `M0 0 H${CW} V${CH} H0 Z`
  const holes = mask
    .filter(r => Array.isArray(r) && r.length >= 4 && r[2] > 0 && r[3] > 0)
    .map(r => {
      const x = r[0] + B, y = r[1] + B
      return `M${x} ${y} H${x + r[2]} V${y + r[3]} H${x} Z`
    }).join(' ')
  return holes ? `${outer} ${holes}` : ''
}

/** 自动缩小字号直到高度装得下（二分法） */
function fitTextHeight(tb: any, maxH: number, minSize: number) {
  const orig = tb.fontSize || 32
  if (tb.height <= maxH) return
  let lo = minSize, hi = orig, best = orig
  for (let i = 0; i < 12; i++) {
    const mid = Math.round((lo + hi) / 2)
    tb.set({ fontSize: mid })
    if (tb.height <= maxH) { best = mid; lo = mid + 1 } else { hi = mid - 1 }
    if (lo > hi) break
  }
  tb.set({ fontSize: Math.max(best, minSize) })
}

/**
 * 竖排文本（竖右：从右往左成列，列内自上而下）。
 * Fabric 无原生竖排，这里按「一列一个 Textbox、字符间插 \n」拼成 Group。
 */
function makeVerticalText(
  text: string, rect: number[], style: any, interactive = true
) {
  const [x, y, w, h] = rect
  const s = style || {}
  const chars = Array.from(text ?? '')
  const lineHeight = s.lineHeight ?? 1.2
  const minFs = s.minFontSize ?? 14
  let fs = s.fontSize ?? 32

  const layout = (fontSize: number) => {
    const colW = Math.ceil(fontSize * 1.45)
    const lineH = fontSize * lineHeight
    const perCol = Math.max(1, Math.floor(h / lineH))
    const nCols = Math.max(1, Math.ceil(chars.length / perCol))
    return { colW, lineH, perCol, nCols, needW: nCols * colW }
  }
  let m = layout(fs)
  if (s.autoShrink !== false) {
    while (m.needW > w && fs > minFs) { fs -= 1; m = layout(fs) }
  }

  const cols: any[] = []
  for (let c = 0; c < m.nCols; c++) {
    const slice = chars.slice(c * m.perCol, (c + 1) * m.perCol)
    const colH = slice.length * m.lineH
    const colTop = s.valign === 'middle' ? y + (h - colH) / 2
      : s.valign === 'bottom' ? y + h - colH : y
    cols.push(new Textbox(slice.join('\n'), {
      left: x + w - (c + 1) * m.colW,
      top: colTop,
      width: m.colW,
      fontSize: fs,
      fontWeight: s.weight ?? 400,
      fill: s.color ?? '#1a1a1a',
      textAlign: 'center',
      lineHeight,
      charSpacing: s.letterSpacing ?? 0,
      fontFamily: s.fontFamily || 'sans-serif',
      stroke: s.stroke || undefined,
      strokeWidth: s.strokeWidth || 0,
      selectable: false,
      evented: false
    }))
  }
  const g = new Group(cols, {
    selectable: interactive,
    evented: interactive,
    subTargetCheck: false,
    interactive: false
  })
  return g
}

function makeText(
  text: string, rect: number[], style: any, interactive = true
) {
  const [x, y, w, h] = rect
  const s = style || {}
  if (s.vertical) return makeVerticalText(text, rect, s, interactive)
  const tb = new Textbox(text ?? '', {
    left: x,
    top: y,
    width: w,
    fontSize: s.fontSize ?? 32,
    fontWeight: s.weight ?? 400,
    fill: s.color ?? '#1a1a1a',
    textAlign: s.align ?? 'left',
    lineHeight: s.lineHeight ?? 1.2,
    charSpacing: s.letterSpacing ?? 0,
    fontFamily: s.fontFamily || 'sans-serif',
    stroke: s.stroke || undefined,
    strokeWidth: s.strokeWidth || 0,
    selectable: interactive,
    evented: interactive,
    splitByGrapheme: true
  })
  if (s.autoShrink !== false) fitTextHeight(tb, h, s.minFontSize ?? 14)
  // 垂直对齐
  const vTop = s.valign === 'middle' ? y + (h - tb.height) / 2
    : s.valign === 'bottom' ? y + h - tb.height : y
  tb.set({ top: vTop })
  return tb
}

/**
 * 隐形定位框：只在编辑器里出现的灰色虚线框 + 名称标签。
 * 它不参与卡牌渲染，用来给 AI 底板流程标注「这里是数值区 / 图片区」。
 */
function makeGuideBox(kind: string, id: string, name: string, box: number[],
                      interactive = true) {
  const [x, y, w, h] = box
  const r = new Rect({
    left: x, top: y, width: w, height: h,
    fill: 'rgba(138,148,166,.10)', stroke: '#8a94a6', strokeWidth: 1.5,
    strokeDashArray: [10, 6], rx: 3, ry: 3,
    selectable: interactive, evented: interactive
  })
  r.data = { kind, id }
  const tag = new Textbox(name, {
    left: x, top: Math.max(0, y - 20), width: Math.max(w, 90),
    fontSize: 14, fill: '#8a94a6',
    backgroundColor: 'rgba(255,255,255,.85)',
    selectable: false, evented: false, splitByGrapheme: true
  })
  tag.data = { kind: 'guideTag', id }
  return [r, tag]
}

/** 字段的"线框"表现：虚线矩形 + 字段名标签 */
function makeWireframe(f: any, box?: number[]) {
  const [x, y, w, h] = box || f.rect
  const color = fieldColor(f.kind)
  const rect = new Rect({
    left: x, top: y, width: w, height: h,
    fill: 'transparent', stroke: color, strokeWidth: 2,
    strokeDashArray: [6, 4], rx: 4, ry: 4,
    selectable: true, evented: true
  })
  rect.data = { kind: 'field', id: f.id, key: f.key }
  return rect
}

/**
 * 把模板（+可选卡牌数据）渲染到 Fabric 画布。
 */
export async function renderTemplate(
  canvas: StaticCanvas, tpl: any, opts: RenderOpts = {}
) {
  const { card, wireframe = false, interactive = true,
    bleedMode = false, guides = false, editor = false } = opts
  const { w: CW, h: CH, offset: B, netW: W, netH: H } = contentSize(tpl, bleedMode)

  // 模板里引用的自定义字体必须先注册，否则量出来的文本宽度/换行都是回退字体的
  await ensureFamiliesIn(tpl)

  canvas.clear()
  canvas.backgroundColor = tpl.background?.color || '#ffffff'

  // 所有内容坐标 = 设计坐标 + 出血偏移
  const off = (r: number[]) => [r[0] + B, r[1] + B, r[2], r[3]] as number[]

  const objs: any[] = []

  // ---- 背景底板 ----
  const bgId = tpl.background?.assetId
  if (bgId) {
    try {
      const bg = await makeBackground(tpl, resolveAsset(bgId), CW, CH, B)
      bg.data = { kind: 'background', id: bgId }
      objs.push(bg)
    } catch { /* 底板缺失时退回纯色 */ }
  }

  // ---- 固定图层 ----
  for (const l of tpl.layers ?? []) {
    if (l.visible === false) continue
    const [x, y, w, h] = off(l.rect)
    if (l.guide) {
      // 隐形定位框：只在编辑器里画虚线占位，卡牌与导出都不渲染
      if (editor) objs.push(...makeGuideBox('layer', l.id, `图层·${l.name}`,
        [x, y, w, h], interactive && !l.locked))
      continue
    }
    if (l.type === 'image' && l.assetId) {
      try {
        const im = await makeImage(resolveAsset(l.assetId), [x, y, w, h], 'cover',
          l.radius || 0, interactive && !l.locked)
        im.set({ opacity: l.opacity ?? 1 })
        im.data = { kind: 'layer', id: l.id }
        objs.push(im)
      } catch { /* ignore */ }
      continue
    }
    if (l.type === 'text' && l.text) {
      const tb = makeText(l.text, [x, y, w, h], l.style, interactive && !l.locked)
      tb.set({ opacity: l.opacity ?? 1 })
      tb.data = { kind: 'layer', id: l.id }
      objs.push(tb)
      continue
    }
    const r = new Rect({
      left: x, top: y, width: w, height: h,
      fill: l.fill ?? 'transparent',
      stroke: l.stroke ?? undefined,
      strokeWidth: l.strokeWidth ?? 0,
      rx: l.radius ?? 0, ry: l.radius ?? 0,
      opacity: l.opacity ?? 1,
      selectable: interactive && !l.locked,
      evented: interactive && !l.locked
    })
    r.data = { kind: 'layer', id: l.id }
    objs.push(r)
  }

  // ---- 字段 ----
  for (const f of tpl.fields ?? []) {
    const raw = f.binding === 'fixed' ? f.value : card?.fields?.[f.key]
    const [x, y, w, h] = off(f.rect)

    if (f.guide) {
      // 隐形定位框：仅编辑器可见（AI 底板流程用它标注区域）
      if (editor) objs.push(...makeGuideBox('field', f.id, `${f.label}（定位）`,
        [x, y, w, h], interactive))
      continue
    }

    if (wireframe) {
      objs.push(makeWireframe(f, [x, y, w, h]))
      const tag = new Textbox(`${f.label}${f.binding === 'fixed' ? ' ·固定' : ''}`, {
        left: x, top: Math.max(0, y - 20), width: Math.max(w, 80),
        fontSize: 14, fill: fieldColor(f.kind),
        backgroundColor: 'rgba(255,255,255,.85)',
        selectable: false, evented: false, splitByGrapheme: true
      })
      tag.data = { kind: 'fieldTag', id: f.id }
      objs.push(tag)
      continue
    }

    if (f.kind === 'image' || f.kind === 'icon') {
      if (raw) {
        try {
          const im = await makeImage(resolveAsset(raw), [x, y, w, h], f.fit || 'cover',
            f.radius || 0, interactive)
          im.data = { kind: 'field', id: f.id, key: f.key }
          objs.push(im)
          continue
        } catch { /* 图缺失则走占位 */ }
      }
      const ph = new Rect({
        left: x, top: y, width: w, height: h,
        fill: 'rgba(0,0,0,.05)', stroke: '#ccc', strokeWidth: 1,
        strokeDashArray: [4, 4], rx: f.radius ?? 0, ry: f.radius ?? 0,
        selectable: interactive, evented: interactive
      })
      ph.data = { kind: 'field', id: f.id, key: f.key }
      objs.push(ph)
      continue
    }

    const text = raw == null || raw === '' ? '' : String(raw)
    if (!text) continue
    const tb = makeText(text, [x, y, w, h], f.style, interactive)
    tb.data = { kind: 'field', id: f.id, key: f.key }
    objs.push(tb)
  }

  // ---- 出血框 / 裁切框 / 安全框（仅编辑器，不参与导出） ----
  if (guides) {
    const safe = safeMargin(tpl)
    if (B > 0) {
      // 裁切线：净尺寸边界（从外扩边界内缩 bleed）
      objs.push(frame(B, B, W, H, '#e5434a', [8, 5], 2))
    }
    // 安全框：净尺寸再内缩 2mm，文字/关键图形不要越界
    objs.push(frame(B + safe, B + safe, W - safe * 2, H - safe * 2,
      '#2fa36b', [3, 4], 1))
  }

  canvas.add(...objs)
  canvas.requestRenderAll()
  return objs
}

/** 参考框（不可选中、不导出） */
function frame(
  x: number, y: number, w: number, h: number,
  color: string, dash: number[], sw: number
) {
  return new Rect({
    left: x, top: y, width: w, height: h,
    fill: 'transparent', stroke: color, strokeWidth: sw,
    strokeDashArray: dash, strokeUniform: true,
    selectable: false, evented: false, hoverCursor: 'default',
    data: { kind: 'guide' }
  })
}

/** 从 fabric 对象反写回 rect（拖动/缩放之后）。
 *  offset = 出血偏移，含出血模式下要把画布坐标减回设计坐标。 */
export function rectFromObject(obj: any, offset = 0): number[] {
  const w = Math.round((obj.width ?? 0) * (obj.scaleX ?? 1))
  const h = Math.round((obj.height ?? 0) * (obj.scaleY ?? 1))
  // 图片是 center 原点、Group 也可能是 center，必须按 origin 换算回左上角
  let left = obj.left ?? 0
  let top = obj.top ?? 0
  if (obj.originX === 'center') left -= w / 2
  else if (obj.originX === 'right') left -= w
  if (obj.originY === 'center') top -= h / 2
  else if (obj.originY === 'bottom') top -= h
  return [Math.round(left - offset), Math.round(top - offset), w, h]
}
