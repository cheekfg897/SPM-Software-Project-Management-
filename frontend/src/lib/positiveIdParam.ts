/**
 * The id a URL parameter holds, or null when it is missing or isn't a whole number from 1. A
 * hand-edited link then reads as no id rather than a bad one.
 */
export function positiveIdParam(params: URLSearchParams, name: string): number | null {
  const id = Number(params.get(name) ?? '')
  return Number.isInteger(id) && id > 0 ? id : null
}
