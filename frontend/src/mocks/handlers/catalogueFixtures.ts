/**
 * Data for the catalogue mock (docs/adr/0032-event-catalogue-contract.md). Every date is
 * fixed, and "now" is fixed too, so unit tests, e2e runs and screenshots see the same page
 * whatever the real date is.
 */

/** The mock backend's "now": Monday 5 October 2026, midday in Singapore. */
export const MOCK_NOW = '2026-10-05T12:00:00+08:00'
export const MOCK_TODAY = '2026-10-05'

export interface MockCatalogueEvent {
  id: number
  reference: string
  name: string
  description: string
  starts_at: string
  ends_at: string
  venue: { id: number; name: string } | null
  capacity: number
  /** Places already taken by people other than the mock users. */
  taken: number
}

const VENUES = {
  ESPLANADE: { id: 1, name: 'Esplanade Outdoor Theatre' },
  FLOWER_DOME: { id: 2, name: 'Gardens by the Bay, Flower Dome' },
  GALLERY: { id: 3, name: 'National Gallery Singapore, Auditorium' },
  CAPITOL: { id: 4, name: 'Capitol Theatre' },
  PROJECTOR: { id: 5, name: 'The Projector, Golden Mile Tower' },
  BOTANIC: { id: 6, name: 'Singapore Botanic Gardens, Symphony Stage' },
  EXPO: { id: 7, name: 'Marina Bay Sands Expo, Hall A' },
  SCIENCE: { id: 8, name: 'Science Centre Singapore, Omni-Theatre' },
} as const

/** name, venue, days after MOCK_TODAY, start time, minutes, capacity, places taken, description */
type EventRow = [
  string,
  MockCatalogueEvent['venue'],
  number,
  string,
  number,
  number,
  number,
  string,
]

const EVENT_ROWS: EventRow[] = [
  [
    'Sunrise Yoga on the Lawn',
    VENUES.BOTANIC,
    0,
    '07:00',
    90,
    80,
    41,
    'A slow flow to start the week, mats provided. Finished by breakfast.',
  ],
  [
    'Lunchtime Talk: Designing for Heat',
    VENUES.GALLERY,
    0,
    '12:30',
    60,
    120,
    88,
    'Architects on building for a city that never cools down.',
  ],
  [
    'Jazz by the Bay',
    VENUES.ESPLANADE,
    0,
    '19:30',
    150,
    200,
    188,
    'An evening of standards and new work from the island’s jazz collectives.',
  ],
  [
    'Night Market Photography Walk',
    null,
    1,
    '19:00',
    120,
    25,
    25,
    'Low light, long lenses, and the best char kway teow stop on the way.',
  ],
  [
    'Startup Pitch Night',
    VENUES.PROJECTOR,
    2,
    '19:00',
    150,
    90,
    37,
    'Ten founders, five minutes each, one very honest panel.',
  ],
  [
    'Orchid Care Masterclass',
    VENUES.FLOWER_DOME,
    3,
    '10:00',
    120,
    40,
    36,
    'Repotting, watering and light, with the Dome’s own growers.',
  ],
  [
    'Friday Film Club: Cosmic Horror',
    VENUES.PROJECTOR,
    4,
    '21:00',
    180,
    110,
    110,
    'A double bill for people who like their space vast and uncaring.',
  ],
  [
    'Family Science Saturday',
    VENUES.SCIENCE,
    5,
    '10:00',
    240,
    300,
    122,
    'Hands-on experiments and a planetarium show for curious kids.',
  ],
  [
    'Symphony in the Gardens',
    VENUES.BOTANIC,
    5,
    '18:00',
    120,
    1500,
    1320,
    'The Singapore Symphony Orchestra outdoors. Bring a picnic.',
  ],
  [
    'Sunday Makers Fair',
    VENUES.EXPO,
    6,
    '11:00',
    360,
    2000,
    740,
    'Two hundred independent makers, from ceramics to hot sauce.',
  ],
  [
    'Data Viz Meetup',
    VENUES.GALLERY,
    8,
    '19:00',
    120,
    80,
    52,
    'Three short talks on charts that tell the truth.',
  ],
  [
    'Heritage Walk: Kampong Glam',
    null,
    9,
    '09:00',
    150,
    30,
    12,
    'Shophouses, surau and the stories behind the textiles on Arab Street.',
  ],
  [
    'Capitol Comedy Night',
    VENUES.CAPITOL,
    11,
    '20:00',
    120,
    900,
    899,
    'Stand-up from across the region. One seat left, and it’s yours.',
  ],
  [
    'Astronomy Night: Saturn at Opposition',
    VENUES.SCIENCE,
    12,
    '19:30',
    150,
    150,
    64,
    'Telescopes on the roof, and an astronomer to point them.',
  ],
  [
    'Floral Arrangement Workshop',
    VENUES.FLOWER_DOME,
    13,
    '14:00',
    120,
    30,
    30,
    'Seasonal blooms and a take-home arrangement.',
  ],
  [
    'Product Design Summit',
    VENUES.EXPO,
    15,
    '09:00',
    480,
    1200,
    455,
    'A day of talks on shipping things people love.',
  ],
  [
    'Poetry at the Gallery',
    VENUES.GALLERY,
    16,
    '19:30',
    90,
    100,
    21,
    'New writing from Singapore poets, read beside the collection.',
  ],
  [
    'Indie Game Showcase',
    VENUES.PROJECTOR,
    18,
    '18:00',
    240,
    150,
    98,
    'Play thirty local games before anyone else does.',
  ],
  [
    'Sunset Choir',
    VENUES.ESPLANADE,
    19,
    '18:30',
    60,
    250,
    70,
    'Free, open-air, and anyone can join in on the last song.',
  ],
  [
    'Climate Futures Forum',
    VENUES.GALLERY,
    20,
    '09:30',
    300,
    180,
    177,
    'Researchers, officials and residents on the next thirty years.',
  ],
  [
    'Craft Beer & Cheese Pairing',
    VENUES.CAPITOL,
    22,
    '19:00',
    120,
    60,
    18,
    'Six local brews, six cheeses, one brewer to explain it all.',
  ],
  [
    'Weekend Kite Festival',
    null,
    26,
    '08:00',
    480,
    5000,
    1300,
    'Marina Barrage roof, all day. Bring a kite or borrow one.',
  ],
  [
    'Writers’ Week Opening',
    VENUES.CAPITOL,
    29,
    '19:00',
    150,
    900,
    410,
    'The festival opens with a conversation between three novelists.',
  ],
  [
    'Mooncake Making Class',
    VENUES.FLOWER_DOME,
    31,
    '15:00',
    120,
    24,
    23,
    'Snowskin and baked, with a pastry chef who has made thousands.',
  ],
  [
    'Accessibility in Tech Meetup',
    VENUES.PROJECTOR,
    33,
    '19:00',
    120,
    100,
    40,
    'Practical talks on building for everyone.',
  ],
  [
    'Deepavali Light Walk',
    null,
    35,
    '19:30',
    120,
    60,
    11,
    'Little India’s lights, with a guide and a sweet stop.',
  ],
  [
    'Chamber Music at Dusk',
    VENUES.GALLERY,
    37,
    '18:30',
    90,
    140,
    139,
    'A string quartet in the rotunda as the light goes down.',
  ],
  [
    'Run the Bay 10K',
    null,
    40,
    '06:30',
    150,
    3000,
    2230,
    'A flat, fast loop of Marina Bay before the heat arrives.',
  ],
  [
    'Year-End Makers Market',
    VENUES.EXPO,
    41,
    '11:00',
    420,
    2500,
    300,
    'Gifts from two hundred makers, and a lot of coffee.',
  ],
  [
    'New Music Now',
    VENUES.ESPLANADE,
    42,
    '20:00',
    120,
    400,
    120,
    'Composers under thirty, premiering work written for this stage.',
  ],
]

const SINGAPORE_OFFSET_MINUTES = 8 * 60

/** The business date `days` after `date` (both YYYY-MM-DD). */
export function addDays(date: string, days: number): string {
  const moment = new Date(`${date}T00:00:00Z`)
  moment.setUTCDate(moment.getUTCDate() + days)
  return moment.toISOString().slice(0, 10)
}

/** A moment as Singapore business time with its offset, e.g. 2026-10-05T19:30:00+08:00. */
function toBusinessTime(moment: Date): string {
  const shifted = new Date(moment.getTime() + SINGAPORE_OFFSET_MINUTES * 60_000)
  return `${shifted.toISOString().slice(0, 19)}+08:00`
}

function toEvent(row: EventRow, index: number): MockCatalogueEvent {
  const [name, venue, dayOffset, startTime, minutes, capacity, taken, description] = row
  const startsAt = `${addDays(MOCK_TODAY, dayOffset)}T${startTime}:00+08:00`
  const endsAt = toBusinessTime(new Date(new Date(startsAt).getTime() + minutes * 60_000))
  const id = index + 1
  return {
    id,
    reference: `EVR-MOCK${String(id).padStart(4, '0')}`,
    name,
    description,
    starts_at: startsAt,
    ends_at: endsAt,
    venue,
    capacity,
    taken,
  }
}

export const MOCK_CATALOGUE_EVENTS: MockCatalogueEvent[] = EVENT_ROWS.map(toEvent)

/** The mock attendee starts out registered for these, so "You're registered" shows. */
export const MOCK_ATTENDEE_REGISTRATIONS: number[] = [
  MOCK_CATALOGUE_EVENTS.find((event) => event.name === 'Startup Pitch Night')?.id ?? 0,
]
