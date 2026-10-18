import { ApiError, NETWORK_ERROR_CODE, NETWORK_ERROR_MESSAGE, toApiError } from './errors'

export type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'

/** Query parameters. Empty strings and `undefined` are left out of the URL. */
export type QueryParams = Record<string, string | number | undefined>

export interface RequestOptions {
  method?: HttpMethod
  body?: unknown
  query?: QueryParams
}

interface SessionHooks {
  /** The signed-in user's access token, or null when signed out. */
  readAccessToken: () => string | null
  /** Called when the backend refuses a token, e.g. because it expired. */
  handleUnauthorised: () => void
}

let sessionHooks: SessionHooks = {
  readAccessToken: () => null,
  // Never called: with no token there's nothing to sign out of (see apiRequest's 401 check).
  /* v8 ignore next -- unreachable until the store connects, and then it's replaced */
  handleUnauthorised: () => undefined,
}

/**
 * Tell the client how to read the session. The store calls this once at start-up, so this
 * module never imports the store.
 */
export function connectApiClient(hooks: SessionHooks): void {
  sessionHooks = hooks
}

/** Where the backend is. In the browser it's the page's own origin (Vite proxies /api). */
function apiOrigin(): string {
  return import.meta.env.VITE_API_ORIGIN ?? window.location.origin
}

function buildUrl(path: string, query: QueryParams = {}): URL {
  const url = new URL(path, apiOrigin())
  for (const [name, value] of Object.entries(query)) {
    if (value !== undefined && value !== '') {
      url.searchParams.set(name, String(value))
    }
  }
  return url
}

function buildHeaders(accessToken: string | null, hasBody: boolean): Headers {
  const headers = new Headers({ Accept: 'application/json' })
  if (hasBody) {
    headers.set('Content-Type', 'application/json')
  }
  if (accessToken) {
    headers.set('Authorization', `Bearer ${accessToken}`)
  }
  return headers
}

async function readJson(response: Response): Promise<unknown> {
  try {
    const body: unknown = await response.json()
    return body
  } catch {
    return null
  }
}

/**
 * Call the backend and return the decoded JSON body.
 *
 * Every request to the backend goes through here. A non-2xx response or a network failure
 * is thrown as an {@link ApiError} carrying the backend's own code and message.
 *
 * `T` is the response shape the caller expects. It's not checked at runtime: the backend
 * defines it, and the integration tests (src/integration) check it against the real backend.
 */
export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, query } = options
  const accessToken = sessionHooks.readAccessToken()
  const hasBody = body !== undefined

  let response: Response
  try {
    response = await fetch(buildUrl(path, query), {
      method,
      headers: buildHeaders(accessToken, hasBody),
      body: hasBody ? JSON.stringify(body) : null,
    })
  } catch {
    throw new ApiError(0, NETWORK_ERROR_CODE, NETWORK_ERROR_MESSAGE)
  }

  if (response.status === 204) {
    return undefined as T
  }

  const responseBody = await readJson(response)
  if (!response.ok) {
    if (response.status === 401 && accessToken) {
      sessionHooks.handleUnauthorised()
    }
    throw toApiError(response.status, responseBody)
  }
  return responseBody as T
}
