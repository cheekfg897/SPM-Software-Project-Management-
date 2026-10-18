/**
 * A name the backend uses, in words: "expected_attendance" reads "Expected attendance". For the
 * names the page shows without a wording of its own, such as a changed field (ADR-0076).
 */
export function humanise(name: string): string {
  const words = name.replaceAll('_', ' ')
  return words.charAt(0).toUpperCase() + words.slice(1)
}
