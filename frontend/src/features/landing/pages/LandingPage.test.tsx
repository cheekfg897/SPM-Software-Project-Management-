import { screen, within } from '@testing-library/react'

import { ROUTES } from '@/config/routes'
import { renderApp } from '@/test/render'

vi.mock('../blackHole/renderer', () => ({ drawScene: vi.fn(), fitCanvas: vi.fn() }))

beforeEach(() => {
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockImplementation(() => null)
})

afterEach(() => vi.restoreAllMocks())

function section(name: string) {
  return within(screen.getByRole('region', { name }))
}

describe('LandingPage', () => {
  it('tells attendees what they can do', () => {
    renderApp(ROUTES.HOME)

    const attendees = section('Find something worth showing up for.')
    expect(attendees.getByText('Discover what’s on')).toBeInTheDocument()
    expect(attendees.getByText('Save your place')).toBeInTheDocument()
    expect(attendees.getByText('Keep your plans together')).toBeInTheDocument()
  })

  it('tells organisers what ConnectSphere does for them', () => {
    renderApp(ROUTES.HOME)

    const organisers = section('Bring the idea. We’ll bring the venue.')
    expect(organisers.getByText('Send a request')).toBeInTheDocument()
    expect(organisers.getByText('We handle the logistics')).toBeInTheDocument()
    expect(organisers.getByText('Always know where it stands')).toBeInTheDocument()
  })

  it('walks through how an event comes together, in order', () => {
    renderApp(ROUTES.HOME)

    const steps = section('From request to registration.').getAllByRole('listitem')
    const stepTitles = steps.map((step) => within(step).getByRole('heading').textContent)
    expect(stepTitles).toEqual(['Request', 'Review', 'Confirmed', 'Registrations open'])
  })

  it('ends by offering both ways in again', () => {
    renderApp(ROUTES.HOME)

    const closing = section('Your next event starts here.')
    expect(closing.getByRole('link', { name: 'Browse events' })).toHaveAttribute(
      'href',
      ROUTES.EVENTS,
    )
    expect(closing.getByRole('link', { name: 'Create an account' })).toHaveAttribute(
      'href',
      ROUTES.SIGN_UP,
    )
  })
})
