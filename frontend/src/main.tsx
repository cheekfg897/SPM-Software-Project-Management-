import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import { App } from './app/App'
import './index.css'

/** `npm run dev:mock` (Vite's "mock" mode) serves the API from src/mocks instead of the backend. */
const IS_MOCK_MODE = import.meta.env.MODE === 'mock'

async function startMockBackend(): Promise<void> {
  if (!IS_MOCK_MODE) {
    return
  }
  const { worker } = await import('./mocks/browser')
  await worker.start({ onUnhandledRequest: 'bypass' })
}

const rootElement = document.getElementById('root')
if (rootElement === null) {
  throw new Error('index.html has no #root element.')
}

void startMockBackend().then(() => {
  createRoot(rootElement).render(
    <StrictMode>
      <App />
    </StrictMode>,
  )
})
