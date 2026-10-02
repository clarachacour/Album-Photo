/**
 * Whether a chosen file is a photo we accept. Some browsers (Windows, some
 * Android phones) don't know the iPhone's HEIC format and give its files no
 * type at all: the file name tells then (the server does the same).
 */
const PHOTO_EXTENSIONS = /\.(jpe?g|png|webp|heic|heif)$/i;

export function isImageFile(file) {
  return Boolean(file) && (file.type?.startsWith("image/") || PHOTO_EXTENSIONS.test(file.name || ""));
}
