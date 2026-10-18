import { screen } from '@testing-library/react'

import type { renderApp } from '@/test/render'

/** As Technical Support on the Equipment page: reserve `quantity` projectors. */
export async function reserveProjectors(
  user: ReturnType<typeof renderApp>['user'],
  quantity: string,
): Promise<void> {
  await user.type(await screen.findByLabelText('Quantity of Projector'), quantity)
  await user.click(screen.getByRole('button', { name: 'Reserve Projector' }))
}
