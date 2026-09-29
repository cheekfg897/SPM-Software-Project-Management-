import { useDispatch, useSelector } from 'react-redux'

import type { AppDispatch, RootState } from './store'

/** `useDispatch` and `useSelector` typed for this store. Use these, not the untyped ones. */
export const useAppDispatch = useDispatch.withTypes<AppDispatch>()
export const useAppSelector = useSelector.withTypes<RootState>()
