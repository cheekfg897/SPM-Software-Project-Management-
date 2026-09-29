import { http, HttpResponse } from 'msw'

import { server } from '@/mocks/server'

import { apiRequest, connectApiClient } from './client'
import { ApiError } from './errors'

function captureRequests(): Request[] {
  const seen: Request[] = []
  server.events.on('request:start', ({ request }) => seen.push(request.clone()))
  return seen
}

afterEach(() => {
  server.events.removeAllListeners()
  connectApiClient({ readAccessToken: () => null, handleUnauthorised: () => undefined })
})

describe('apiRequest', () => {
  it('returns the JSON body of a successful response', async () => {
    server.use(http.get('/api/things', () => HttpResponse.json({ id: 1 })))

    await expect(apiRequest('/api/things')).resolves.toEqual({ id: 1 })
  })

  it('sends a JSON body with the method given', async () => {
    const requests = captureRequests()
    server.use(http.post('/api/things', () => HttpResponse.json({}, { status: 201 })))

    await apiRequest('/api/things', { method: 'POST', body: { name: 'Gala' } })

    const [request] = requests
    expect(request?.headers.get('Content-Type')).toBe('application/json')
    expect(await request?.json()).toEqual({ name: 'Gala' })
  })

  it('adds query parameters, leaving out empty ones', async () => {
    const requests = captureRequests()
    server.use(http.get('/api/things', () => HttpResponse.json([])))

    await apiRequest('/api/things', { query: { q: 'jazz', page: 2, from: '', to: undefined } })

    const url = new URL(requests[0]?.url ?? '')
    expect(url.searchParams.toString()).toBe('q=jazz&page=2')
  })

  it('returns undefined for a response with no content', async () => {
    server.use(http.delete('/api/things/1', () => new HttpResponse(null, { status: 204 })))

    await expect(apiRequest('/api/things/1', { method: 'DELETE' })).resolves.toBeUndefined()
  })

  it('sends the access token when there is one', async () => {
    const requests = captureRequests()
    connectApiClient({ readAccessToken: () => 'abc', handleUnauthorised: () => undefined })
    server.use(http.get('/api/things', () => HttpResponse.json({})))

    await apiRequest('/api/things')

    expect(requests[0]?.headers.get('Authorization')).toBe('Bearer abc')
  })

  it('sends no Authorization header when signed out', async () => {
    const requests = captureRequests()
    server.use(http.get('/api/things', () => HttpResponse.json({})))

    await apiRequest('/api/things')

    expect(requests[0]?.headers.has('Authorization')).toBe(false)
  })

  it('throws the backend error as an ApiError', async () => {
    server.use(
      http.get('/api/things', () =>
        HttpResponse.json({ error: 'not_found', message: 'No such thing.' }, { status: 404 }),
      ),
    )

    const error = await apiRequest('/api/things').catch((caught: unknown) => caught)

    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({ status: 404, code: 'not_found', message: 'No such thing.' })
  })

  it('throws a generic error when an error response has no JSON body', async () => {
    server.use(http.get('/api/things', () => new HttpResponse('Bad gateway', { status: 502 })))

    await expect(apiRequest('/api/things')).rejects.toMatchObject({
      status: 502,
      code: 'unexpected_response',
    })
  })

  it('signs the user out when a request with a token is refused as unauthenticated', async () => {
    const handleUnauthorised = vi.fn()
    connectApiClient({ readAccessToken: () => 'expired', handleUnauthorised })
    server.use(
      http.get('/api/things', () =>
        HttpResponse.json({ error: 'authentication_error', message: 'Expired.' }, { status: 401 }),
      ),
    )

    await expect(apiRequest('/api/things')).rejects.toBeInstanceOf(ApiError)
    expect(handleUnauthorised).toHaveBeenCalledOnce()
  })

  it('does not sign anyone out when a 401 comes back to a request without a token', async () => {
    const handleUnauthorised = vi.fn()
    connectApiClient({ readAccessToken: () => null, handleUnauthorised })
    server.use(
      http.post('/api/auth/login', () =>
        HttpResponse.json({ error: 'authentication_error', message: 'Wrong.' }, { status: 401 }),
      ),
    )

    await expect(apiRequest('/api/auth/login', { method: 'POST', body: {} })).rejects.toThrow(
      'Wrong.',
    )
    expect(handleUnauthorised).not.toHaveBeenCalled()
  })

  it('throws a network error when the backend cannot be reached', async () => {
    server.use(http.get('/api/things', () => HttpResponse.error()))

    await expect(apiRequest('/api/things')).rejects.toMatchObject({
      status: 0,
      code: 'network_error',
      message: "Can't reach ConnectSphere. Check your connection and try again.",
    })
  })
})
