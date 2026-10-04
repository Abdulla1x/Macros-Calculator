/**
 * The arithmetic and the decisions behind shrinking a meal photo before upload.
 *
 * Kept free of the DOM on purpose, so it runs under `node --test` with no
 * browser and no test framework. lib/photoDownscale.ts is the half that needs a
 * canvas; everything that can be wrong without one lives here.
 *
 * Why shrink at all: a phone photo is 3-8 MB, the server forwards it to Gemini
 * as base64 on every retry, and Gemini then cuts it down to a fixed token
 * budget anyway (1120 tokens per image on Gemini 3, whatever the pixel count).
 * The extra megapixels bought nothing but upload seconds, most of the free
 * tier's monthly bandwidth, and a memory spike on a 512 MB server.
 */

/** The longest side a photo is sent at, in pixels.
 *
 * Chosen by a measured A/B, not by taste: downscaling changes what the model
 * sees, so it is an accuracy decision. Seven real meal photos (five plates, two
 * nutrition labels), sent photo-only through the production model at full size,
 * 1536 and 1024, and compared with the model's own run-to-run noise
 * (backend/scripts/compare_estimates.py):
 *
 *   - 1024 read plates HIGHER and never lower -- +51% on one dish, +15% on two
 *     more -- with ranges 13% wider. Rejected, although it is half the bytes.
 *   - 1536 landed on both sides of the full-size estimates (median difference
 *     a few percent, ranges the same width), and its repeats were stable.
 *   - Labels read identically at every size; plates are where detail matters.
 *
 * Gemini billed the same 1,870 prompt tokens at every size, so this is not a
 * cost choice: its own resize evidently keeps more than 1024 px. 1536 is also
 * the size at which the 2.5-generation fallback's 768 px tiles are native.
 * A 10 MP phone photo comes out at roughly 150-240 KB, 11-14x smaller.
 */
export const MAX_LONG_EDGE = 1536

/** JPEG quality for the re-encode, on the canvas API's 0-1 scale. */
export const JPEG_QUALITY = 0.8

/** The size to draw an image at so its long edge is at most `maxEdge`.
 *
 * Never upscales: an image already inside the limit comes back at its own size,
 * because enlarging adds bytes and no detail. Never returns a zero side either,
 * since a 4000x1 strip scaled down would round its short side to nothing and a
 * zero-sized canvas encodes to an empty file.
 */
export function fitWithin(
  width: number,
  height: number,
  maxEdge: number,
): { width: number; height: number } {
  const longEdge = Math.max(width, height)
  if (longEdge <= maxEdge) return { width, height }
  const scale = maxEdge / longEdge
  return {
    width: Math.max(1, Math.round(width * scale)),
    height: Math.max(1, Math.round(height * scale)),
  }
}

/** Whether the re-encoded photo should be sent instead of the original.
 *
 * Only when it is actually smaller. A small, already-compressed image can come
 * out of a q80 re-encode *bigger* than it went in, and the whole point of this
 * is fewer bytes -- so in that case the original wins, untouched.
 */
export function preferEncoded(originalBytes: number, encodedBytes: number): boolean {
  return encodedBytes > 0 && encodedBytes < originalBytes
}

/** The filename to give the re-encoded bytes.
 *
 * `IMG_1234.HEIC` becomes `IMG_1234.jpg`. The server forwards the browser's
 * content type rather than guessing from the name, so this is not what makes
 * the upload work; it keeps the two from contradicting each other in a log or
 * a multipart dump, where a ".heic" holding JPEG bytes reads like a bug.
 */
export function jpegName(name: string): string {
  const dot = name.lastIndexOf('.')
  const stem = dot > 0 ? name.slice(0, dot) : name
  return `${stem || 'photo'}.jpg`
}
