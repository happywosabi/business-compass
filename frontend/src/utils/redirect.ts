/**
 * 登录后要回到的页面（网址里的 ?redirect=...）。
 *
 * 只允许本站内的路径。否则别人可以发一个「登录链接」，让用户登录后被带到假冒网站
 * （开放重定向漏洞）。
 */
export function safeRedirect(raw: unknown, fallback = '/'): string {
  const value = Array.isArray(raw) ? raw[0] : raw
  if (typeof value !== 'string') return fallback
  // 必须是本站路径：以「/」开头，但不能是「//」或「/\」（浏览器会把它们当成别的网站）
  if (!value.startsWith('/') || value.startsWith('//') || value.startsWith('/\\')) return fallback
  // 不允许控制字符（换行、制表符等）
  if (/[\u0000-\u001f\u007f]/.test(value)) return fallback
  // 不回到登录、注册页本身，避免来回跳
  if (/^\/(login|register)(?:[/?#]|$)/.test(value)) return fallback
  return value
}
