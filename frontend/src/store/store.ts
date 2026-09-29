import { configureStore } from '@reduxjs/toolkit'

import { connectApiClient } from '@/lib/api'

import { loadSession, saveSession } from './persistedSession'
import { selectAccessToken, sessionReducer, signedOut } from './sessionSlice'

/**
 * Build the store, starting from the saved session. It also connects the API client to
 * the session, so requests carry the token and a refused token signs the user out.
 */
export function createAppStore() {
  const store = configureStore({
    reducer: { session: sessionReducer },
    preloadedState: { session: loadSession() },
  })

  store.subscribe(() => saveSession(store.getState().session))

  connectApiClient({
    readAccessToken: () => selectAccessToken(store.getState()),
    handleUnauthorised: () => store.dispatch(signedOut()),
  })

  return store
}

export type AppStore = ReturnType<typeof createAppStore>
export type RootState = ReturnType<AppStore['getState']>
export type AppDispatch = AppStore['dispatch']
