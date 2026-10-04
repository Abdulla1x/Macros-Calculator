import { fitWithin, JPEG_QUALITY, jpegName, MAX_LONG_EDGE, preferEncoded } from './photoSize'

/**
 * Shrink a meal photo in the browser before it is uploaded for analysis.
 *
 * The canvas half of lib/photoSize.ts: that file decides the size and whether
 * the result is worth sending, this one does the decoding and encoding it
 * cannot do without a DOM. See photoSize.ts for why photos are shrunk at all.
 *
 * Side effect worth knowing: re-encoding through a canvas writes no EXIF, so
 * a shrunk photo no longer carries the phone's GPS position or camera details.
 * The original still does -- which is what is sent whenever shrinking fails.
 */

// One photo at a time, however many are picked at once. A decoded 12 MP photo
// is about 48 MB of pixels; four decoded in parallel would be ~200 MB, on the
// kind of low-end phone that can least afford it. Chaining also keeps the
// work in pick order.
let queue: Promise<unknown> = Promise.resolve()

// "Never blocks the upload" has to cover a hang as well as an error: Analyze
// waits for this, so a decoder that never answered would freeze the button.
// Generous, because a slow phone really can take a few seconds per photo.
const SHRINK_TIMEOUT_MS = 15_000

/** The photo to upload in place of `file`: smaller if possible, else `file`.
 *
 * Never rejects. Every failure -- a format this browser cannot decode (HEIC in
 * Chrome on Android), a missing API, an encoder that does not do JPEG -- falls
 * back to the original, because a slow upload is a much smaller problem than a
 * meal that cannot be analysed at all. The server still accepts originals up
 * to its own size limit; the model accepts HEIC.
 *
 * `maxEdge` is a parameter only so the size A/B can run the exact code that
 * ships at more than one size; the app always uses the default.
 */
export function downscaleForUpload(file: File, maxEdge = MAX_LONG_EDGE): Promise<File> {
  const result = queue.then(() =>
    Promise.race([
      shrink(file, maxEdge),
      new Promise<File>((resolve) => setTimeout(() => resolve(file), SHRINK_TIMEOUT_MS)),
    ]),
  )
  queue = result.catch(() => undefined)
  return result.catch(() => file)
}

async function shrink(file: File, maxEdge: number): Promise<File> {
  // 'from-image' applies the EXIF orientation while decoding. Phones store most
  // photos sideways with a flag saying which way is up; the canvas has no such
  // flag, so ignoring it would send the model a plate on its side.
  const bitmap = await createImageBitmap(file, { imageOrientation: 'from-image' })
  const canvas = document.createElement('canvas')
  try {
    const { width, height } = fitWithin(bitmap.width, bitmap.height, maxEdge)
    canvas.width = width
    canvas.height = height
    const context = canvas.getContext('2d')
    if (!context) return file
    // JPEG has no transparency. Without a background a transparent PNG's
    // see-through pixels encode as black, which reads as a burnt plate.
    context.fillStyle = '#fff'
    context.fillRect(0, 0, width, height)
    // A single large step down (4000 px to 1024) aliases fine detail -- text
    // on a packet's label first -- unless the browser is asked for its best
    // resampling rather than its fastest.
    context.imageSmoothingQuality = 'high'
    context.drawImage(bitmap, 0, 0, width, height)

    const blob = await new Promise<Blob | null>((resolve) =>
      canvas.toBlob(resolve, 'image/jpeg', JPEG_QUALITY),
    )
    // A browser that cannot encode the requested type does not fail: it hands
    // back a PNG instead, which for a photo is often larger than the original.
    if (!blob || blob.type !== 'image/jpeg') return file
    if (!preferEncoded(file.size, blob.size)) return file
    return new File([blob], jpegName(file.name), {
      type: 'image/jpeg',
      lastModified: file.lastModified,
    })
  } finally {
    // Released now rather than whenever the collector gets to them. The
    // bitmap's pixels are the bulk of the peak; a canvas keeps its backing
    // store until it is resized to nothing.
    bitmap.close()
    canvas.width = 0
    canvas.height = 0
  }
}
