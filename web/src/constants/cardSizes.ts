/**
 * 常见桌游卡牌尺寸预设（新建模板时选）。
 *
 * 全部以**毫米**为准，像素按 `mm / 25.4 × dpi` 换算 —— 印刷看的是物理尺寸，
 * DPI 只是同一物理量在不同精度下的采样密度。
 * 出血固定 3mm（印刷行业惯例），换算成像素 = `3 / 25.4 × dpi`。
 */
export const MM = 25.4
export const BLEED_MM = 3

export interface CardSize {
  id: string
  name: string
  /** 常见叫法/用途，帮用户选 */
  hint: string
  w_mm: number
  h_mm: number
}

export const CARD_SIZES: CardSize[] = [
  { id: 'poker', name: '标准扑克 63×88', hint: '万智牌 / 大部分桌游的标准卡', w_mm: 63, h_mm: 88 },
  { id: 'ygo', name: '游戏王 59×86', hint: '略窄一点的标准卡', w_mm: 59, h_mm: 86 },
  { id: 'bridge', name: '桥牌 57×89', hint: '细长，常见于扑克类', w_mm: 57, h_mm: 89 },
  { id: 'mini', name: '迷你卡 44×67', hint: '小卡 / 配件卡 / 指示物', w_mm: 44, h_mm: 67 },
  { id: 'tarot', name: '大卡·塔罗 70×120', hint: '塔罗 / 展示用大卡', w_mm: 70, h_mm: 120 },
  { id: 'square', name: '方形卡 70×70', hint: '方形卡 / 版图块', w_mm: 70, h_mm: 70 },
  { id: 'oversize', name: '超大卡 88×126', hint: '角色大卡 / 首领卡', w_mm: 88, h_mm: 126 },
  { id: 'custom', name: '自定义尺寸', hint: '手动填毫米数', w_mm: 63, h_mm: 88 }
]

/** 毫米 → 像素（四舍五入） */
export const mmToPx = (mm: number, dpi: number) => Math.round((mm / MM) * dpi)

/** 由毫米尺寸 + DPI 生成模板 canvas 规格 */
export function canvasSpec(w_mm: number, h_mm: number, dpi = 300) {
  return {
    w: mmToPx(w_mm, dpi),
    h: mmToPx(h_mm, dpi),
    dpi,
    bleed: mmToPx(BLEED_MM, dpi),
    w_mm: Number(w_mm.toFixed(1)),
    h_mm: Number(h_mm.toFixed(1))
  }
}

/** 含出血后的实际物理尺寸（展示用） */
export function bleedSizeText(c: any) {
  const w = (c?.w_mm ?? 63) + BLEED_MM * 2
  const h = (c?.h_mm ?? 88) + BLEED_MM * 2
  return `${c?.w ?? 0}×${c?.h ?? 0}px · ${(c?.w_mm ?? 63)}×${(c?.h_mm ?? 88)}mm（含出血 ${w}×${h}mm）`
}
