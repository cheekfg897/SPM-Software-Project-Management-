/**
 * What a call failed with (an ApiError, for a refusal from the mock backend), or what it
 * resolved to if it didn't fail, so `expect(...).toMatchObject({ status: 404 })` fails then.
 */
export function refusal(call: Promise<unknown>): Promise<unknown> {
  return call.catch((caught: unknown) => caught)
}
