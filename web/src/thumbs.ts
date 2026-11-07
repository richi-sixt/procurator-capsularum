// Bildvorschau: Endungen, die der Server als Vorschaubild liefern kann, und die Adresse dazu.
const IMAGE = new Set(['.jpg', '.jpeg', '.png', '.webp', '.heic', '.heif', '.tif', '.tiff', '.bmp', '.gif'])

export const isImage = (name: string): boolean => {
  const i = name.lastIndexOf('.')
  return i >= 0 && IMAGE.has(name.slice(i).toLowerCase())
}

export const thumbUrl = (path: string, size = 96): string =>
  `/api/thumb?path=${encodeURIComponent(path)}&size=${size}`
