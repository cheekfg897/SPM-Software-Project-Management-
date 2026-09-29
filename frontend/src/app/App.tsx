import { QueryClientProvider } from '@tanstack/react-query'
import { Provider } from 'react-redux'
import { createBrowserRouter } from 'react-router'
import { RouterProvider } from 'react-router/dom'

import { createAppStore } from '@/store'

import { createQueryClient } from './queryClient'
import { appRoutes } from './routes'

const store = createAppStore()
const queryClient = createQueryClient()
const router = createBrowserRouter(appRoutes)

export function App() {
  return (
    <Provider store={store}>
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </Provider>
  )
}
