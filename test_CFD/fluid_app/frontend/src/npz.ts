import { unzipSync } from 'fflate'
import { fromArrayBuffer } from 'numpy-parser'

export type NpyArray = {
  data: Float32Array | Float64Array | Int32Array | Uint8Array | Uint16Array | Int16Array
  shape: number[]
}

function toArrayBuffer(u8: Uint8Array): ArrayBuffer {
  // Some runtimes type this as ArrayBuffer|SharedArrayBuffer; numpy-parser expects ArrayBuffer.
  return u8.slice().buffer
}

export function parseNpz(buffer: ArrayBuffer): Record<string, NpyArray> {
  const u8 = new Uint8Array(buffer)
  const files = unzipSync(u8)

  const out: Record<string, NpyArray> = {}
  for (const [name, bytes] of Object.entries(files)) {
    const arr = fromArrayBuffer(toArrayBuffer(bytes as Uint8Array)) as any

    // numpy-parser returns: { data: TypedArray, shape: number[], ... }
    out[name.replace(/\.npy$/i, '')] = {
      data: arr.data,
      shape: arr.shape,
    }
  }
  return out
}
