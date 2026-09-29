/** True for a plain object, e.g. decoded JSON, so its fields can be read and then checked. */
export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}
