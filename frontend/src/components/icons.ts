/**
 * 线条图标（24×24，描边）。自己画而不用 Vant 的图标字体，是为了和罗盘风格统一。
 * 每个图标由几段形状组成：path 写 d 属性，circle 写圆心和半径，rect 写位置、大小和圆角。
 */

export type Shape =
  | { path: string }
  | { circle: [cx: number, cy: number, r: number]; fill?: boolean }
  | { rect: [x: number, y: number, width: number, height: number, radius: number] }

export const ICONS = {
  profiles: [{ rect: [5, 3, 14, 18, 2.5] }, { path: 'M9 8h6M9 12h6M9 16h3.5' }],
  content: [{ path: 'M4.5 19.5l1.1-4.4L15.4 5.3a2 2 0 0 1 2.8 0l.5.5a2 2 0 0 1 0 2.8L8.9 18.4z' }, { path: 'M4 21h16' }],
  user: [{ circle: [12, 8.5, 3.8] }, { path: 'M4.5 20c.9-3.6 3.9-5.5 7.5-5.5s6.6 1.9 7.5 5.5' }],
  eye: [{ path: 'M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z' }, { circle: [12, 12, 3] }],
  'eye-off': [
    { path: 'M3.5 3.5l17 17' },
    { path: 'M10.6 5.6A10 10 0 0 1 12 5.5c6 0 9.5 6.5 9.5 6.5a17 17 0 0 1-2.9 3.7M6.6 6.7C3.9 8.4 2.5 12 2.5 12S6 18.5 12 18.5a9.6 9.6 0 0 0 4.6-1.2' },
    { path: 'M9.9 9.9a3 3 0 0 0 4.2 4.2' },
  ],
  alert: [{ circle: [12, 12, 9] }, { path: 'M12 7.5v5.5' }, { circle: [12, 16.4, 0.4], fill: true }],
  check: [{ path: 'M5 12.5l4.5 4.5L19 7.5' }],
  mail: [{ rect: [3, 5.5, 18, 13, 2] }, { path: 'M3.5 7l8.5 6 8.5-6' }],
  lock: [{ rect: [5, 10.5, 14, 10, 2] }, { path: 'M8 10.5V7.5a4 4 0 0 1 8 0v3' }],
  logout: [{ path: 'M14 4.5H6.5a2 2 0 0 0-2 2v11a2 2 0 0 0 2 2H14' }, { path: 'M10 12h10M16.5 8.5 20 12l-3.5 3.5' }],
  doc: [{ path: 'M6 3h8l4 4v14H6z' }, { path: 'M14 3v4h4M9 12h6M9 16h6' }],
  'chevron-left': [{ path: 'M14.5 5.5 8 12l6.5 6.5' }],
  'chevron-right': [{ path: 'M9.5 5.5 16 12l-6.5 6.5' }],
  plus: [{ path: 'M12 5v14M5 12h14' }],
} satisfies Record<string, Shape[]>

export type IconName = keyof typeof ICONS
