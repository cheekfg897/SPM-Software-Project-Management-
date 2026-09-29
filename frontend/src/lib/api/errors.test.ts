import { ApiError, errorMessageOf, fieldErrorsOf, toApiError } from './errors'

describe('toApiError', () => {
  it('keeps the code and message from the backend error body', () => {
    const error = toApiError(403, { error: 'authorization_error', message: 'Not allowed.' })

    expect(error).toBeInstanceOf(ApiError)
    expect(error.status).toBe(403)
    expect(error.code).toBe('authorization_error')
    expect(error.message).toBe('Not allowed.')
    expect(error.fieldErrors).toEqual({})
  })

  it('turns validation details into messages per field', () => {
    const error = toApiError(400, {
      error: 'validation_error',
      message: 'Invalid request.',
      details: { email: ['Not a valid email address.'], password: ['Too short.', 'No digit.'] },
    })

    expect(error.fieldErrors).toEqual({
      email: ['Not a valid email address.'],
      password: ['Too short.', 'No digit.'],
    })
  })

  it('names a nested field by its dotted path', () => {
    const error = toApiError(400, {
      error: 'validation_error',
      message: 'Invalid request.',
      details: { venue: { capacity: ['Must be positive.'] } },
    })

    expect(error.fieldErrors).toEqual({ 'venue.capacity': ['Must be positive.'] })
  })

  it('ignores detail values that are not lists of messages', () => {
    const error = toApiError(409, {
      error: 'conflict',
      message: 'Clashes.',
      details: { overlapping: [{ id: 1 }], count: 2 },
    })

    expect(error.fieldErrors).toEqual({})
  })

  it('falls back to a generic error when the body is not the backend shape', () => {
    const error = toApiError(502, '<html>Bad gateway</html>')

    expect(error.code).toBe('unexpected_response')
    expect(error.message).toBe('Something went wrong. Please try again.')
  })
})

describe('ApiError.isClientError', () => {
  it('is true for a 4xx status and false otherwise', () => {
    expect(toApiError(404, null).isClientError).toBe(true)
    expect(toApiError(500, null).isClientError).toBe(false)
    expect(toApiError(0, null).isClientError).toBe(false)
  })
})

describe('errorMessageOf and fieldErrorsOf', () => {
  it('read an ApiError', () => {
    const error = new ApiError(400, 'validation_error', 'Invalid request.', { email: ['Bad.'] })

    expect(errorMessageOf(error)).toBe('Invalid request.')
    expect(fieldErrorsOf(error)).toEqual({ email: ['Bad.'] })
  })

  it('fall back for anything else', () => {
    expect(errorMessageOf(new Error('internal detail'))).toBe(
      'Something went wrong. Please try again.',
    )
    expect(fieldErrorsOf(null)).toEqual({})
  })
})
