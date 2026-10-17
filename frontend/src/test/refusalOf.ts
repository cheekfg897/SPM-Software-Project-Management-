import { ApiError } from '@/lib/api'

/** The ApiError a call was refused with. Fails the test if it succeeded or failed another way. */
export async function refusalOf(call: Promise<unknown>): Promise<ApiError> {
  const error: unknown = await call.then(
    () => null,
    (caught: unknown) => caught,
  )
  if (!(error instanceof ApiError)) {
    throw new Error('Expected the request to be refused with an ApiError.')
  }
  return error
}
