const placeholderPattern = /【待填：[^【】\n]+】/g

export function pendingFields(content: string): string[] {
  return [...new Set(content.match(placeholderPattern) ?? [])]
}

export function fillField(content: string, field: string, value: string): string {
  if (!value.trim() || pendingFields(value).length) return content
  return content.split(field).join(value.trim())
}

export function removeFieldLine(content: string, field: string): string {
  return content
    .split('\n')
    .filter((line) => !line.includes(field))
    .join('\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}
