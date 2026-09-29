/** The text typed into the form field called `name` ('' when there is no such field). */
export function formText(form: FormData, name: string): string {
  const value = form.get(name)
  return typeof value === 'string' ? value : ''
}
