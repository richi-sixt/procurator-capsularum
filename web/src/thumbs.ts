// Vorschau: Endungen, für die der Server ein Vorschaubild liefern kann (Bilder, bei PDF die erste Seite).
const IMAGE = new Set(['.jpg', '.jpeg', '.png', '.webp', '.heic', '.heif', '.tif', '.tiff', '.bmp', '.gif', '.pdf'])

export const isPreviewable = (name: string): boolean => {
  const i = name.lastIndexOf('.')
  return i >= 0 && IMAGE.has(name.slice(i).toLowerCase())
}

export const thumbUrl = (path: string, size = 96): string =>
  `/api/thumb?path=${encodeURIComponent(path)}&size=${size}`
