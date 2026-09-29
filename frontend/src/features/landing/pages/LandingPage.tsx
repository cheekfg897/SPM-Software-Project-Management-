import { AudienceSection } from '../components/AudienceSection'
import type { AudiencePoint } from '../components/AudienceSection'
import { BlackHoleHero } from '../components/BlackHoleHero'
import { ClosingCta } from '../components/ClosingCta'
import { JourneySection } from '../components/JourneySection'

/** What attendees can do (SCRUM-52, SCRUM-53, SCRUM-54). */
const ATTENDEE_POINTS: AudiencePoint[] = [
  {
    title: 'Discover what’s on',
    body: 'Browse upcoming events, narrow them down by date, or search for the one a friend mentioned.',
  },
  {
    title: 'Save your place',
    body: 'Register with your ConnectSphere account. When an event is full, it says so.',
  },
  {
    title: 'Keep your plans together',
    body: 'See every event you’ve registered for, and withdraw if your plans change.',
  },
]

/** What ConnectSphere does for organisers (SCRUM-19, SCRUM-20, SCRUM-22, SCRUM-30, SCRUM-32). */
const ORGANISER_POINTS: AudiencePoint[] = [
  {
    title: 'Send a request',
    body: 'Tell us the date, the expected crowd and what you need. Keep it as a draft until it’s ready.',
  },
  {
    title: 'We handle the logistics',
    body: 'A dedicated coordinator reviews your request, books a venue that suits it and reserves the equipment.',
  },
  {
    title: 'Always know where it stands',
    body: 'Follow your request from submitted to confirmed, and answer your coordinator’s questions in one place.',
  },
]

export function LandingPage() {
  return (
    <main>
      <BlackHoleHero />
      <AudienceSection
        eyebrow="For attendees"
        title="Find something worth showing up for."
        description="Talks, workshops, launches and nights out, all in one calendar."
        points={ATTENDEE_POINTS}
      />
      <AudienceSection
        eyebrow="For organisers"
        title="Bring the idea. We’ll bring the venue."
        description="ConnectSphere’s event committee turns your request into a confirmed event."
        points={ORGANISER_POINTS}
      />
      <JourneySection />
      <ClosingCta />
    </main>
  )
}
