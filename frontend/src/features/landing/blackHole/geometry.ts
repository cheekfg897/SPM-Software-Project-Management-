/**
 * The black hole in the landing page hero, as plain numbers: no canvas, no DOM.
 *
 * Distances are in "disk units", where the black hole's shadow has a radius of 1. The
 * camera turns disk units into pixels. Angles go round the disk in radians, with angle 0
 * pointing right and angle π/2 pointing at the viewer (the near side). The renderer
 * (renderer.ts) draws whatever these functions work out.
 */

export const SHADOW_RADIUS = 1
export const DISK_INNER_RADIUS = 1.35
export const DISK_OUTER_RADIUS = 6

/** Only the inner part of the disk is bright enough to show in the lensed arc. */
const LENSED_OUTER_RADIUS = 3.2
/** The lensed arc runs from just outside the shadow to under half a shadow further out. */
export const LENSED_ARC_INNER = 1.03
export const LENSED_ARC_OUTER = 1.42
/** Only points well behind the hole are lensed over the top; near the sides they'd show
 *  as vertical ticks where the arc meets the disk. */
const LENSED_MIN_DEPTH = 0.35

const PARTICLE_COUNT = 3200
const STAR_COUNT = 260
/**
 * Particle colours are rounded to this many bands across the disk, and their brightness
 * to steps of ALPHA_STEP, so a few dozen colours cover every particle and each colour is
 * drawn in one stroke.
 */
const COLOUR_BANDS = 16
const ALPHA_STEP = 0.1

/** Radians per second at radius 1. Real discs follow Kepler, so speed falls as r^-1.5. */
const BASE_ORBITAL_SPEED = 0.9

/** How far the disk's outer edge reaches past the edge of the viewport, at full zoom. */
const OUTER_EDGE_SPILL = 1.35
/** A tall screen is sized as if it were this much wider, so phones still get a big disk. */
const PORTRAIT_SPAN_FACTOR = 1.2

/** The camera at the top of the page (progress 0) and after the hero (progress 1). */
const TILT_AT_TOP = 0.18
const TILT_AT_BOTTOM = 0.32
const ZOOM_AT_TOP = 1
const ZOOM_AT_BOTTOM = 0.62
/** The hole starts low, under the headline, and rises to the middle as the words lift away. */
const CENTRE_HEIGHT_AT_TOP = 0.72
const CENTRE_HEIGHT_AT_BOTTOM = 0.52
/** Scrolling through the hero fast-forwards the disk by this many seconds: the swirl. */
const SCROLL_SWIRL_SECONDS = 16
/** The nearest stars drift up by this share of the screen over the hero. */
const STAR_DRIFT_AT_BOTTOM = 0.35

export interface Rgb {
  red: number
  green: number
  blue: number
}

interface ColourStop {
  /** Share of the way from the inner edge (0) to the outer edge (1). */
  at: number
  colour: Rgb
}

/** The disk's colours, inside to out: hot cream, pale gold, orange, red, violet, deep violet. */
const INNER_EDGE_STOP: ColourStop = { at: 0, colour: { red: 255, green: 241, blue: 214 } }
const MIDDLE_STOPS: ColourStop[] = [
  { at: 0.15, colour: { red: 255, green: 212, blue: 154 } },
  { at: 0.35, colour: { red: 255, green: 154, blue: 60 } },
  { at: 0.6, colour: { red: 224, green: 69, blue: 43 } },
  { at: 0.8, colour: { red: 138, green: 77, blue: 189 } },
]
const OUTER_EDGE_STOP: ColourStop = { at: 1, colour: { red: 58, green: 29, blue: 92 } }

export interface DiskParticle {
  radius: number
  startAngle: number
  /** Radians per second. */
  angularSpeed: number
  /** How far the streak trails behind the particle, in radians. */
  length: number
  /** A ready-made `rgba(...)` string, so no colour is worked out while drawing. */
  colour: string
}

export interface Star {
  /** Position as a share of the screen's width and height, 0 to 1. */
  x: number
  y: number
  /** Pixels. */
  size: number
  alpha: number
  /** 1 for the nearest stars, which drift furthest when scrolling. */
  depth: number
}

/** Particles that share a colour, drawn together. */
export interface ParticleBatch {
  colour: string
  particles: DiskParticle[]
}

export interface Scene {
  batches: ParticleBatch[]
  stars: Star[]
}

/** What the scroll position asks of the camera. */
export interface View {
  tilt: number
  zoom: number
  /** Where the black hole's centre sits, as a share of the screen's height. */
  centreHeight: number
  /** Seconds added to the disk's clock, so scrolling spins it on. */
  diskTimeOffset: number
  /** How far the nearest stars have drifted up, as a share of the screen's height. */
  starDrift: number
}

/** A view placed on a screen of a given size. */
export interface Camera {
  centreX: number
  centreY: number
  /** Pixels per disk unit. */
  scale: number
  /** 0 is exactly edge-on, 1 is looking straight down on the disk. */
  tilt: number
}

export interface Point {
  x: number
  y: number
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max)
}

function lerp(from: number, to: number, amount: number): number {
  return from + (to - from) * amount
}

/** Slow at both ends, faster in the middle, so the camera settles rather than stops. */
function easeInOutCubic(amount: number): number {
  if (amount < 0.5) {
    return 4 * amount ** 3
  }
  return 1 - (-2 * amount + 2) ** 3 / 2
}

/**
 * A seeded random number generator (mulberry32). The same seed always builds the same
 * disk, so the hero looks the same on every visit and in every test.
 */
export function createRandom(seed: number): () => number {
  let state = seed >>> 0
  return () => {
    state = (state + 0x6d2b79f5) >>> 0
    let mixed = state
    mixed = Math.imul(mixed ^ (mixed >>> 15), mixed | 1)
    mixed ^= mixed + Math.imul(mixed ^ (mixed >>> 7), mixed | 61)
    return ((mixed ^ (mixed >>> 14)) >>> 0) / 4294967296
  }
}

function mixStops(lower: ColourStop, upper: ColourStop, at: number): Rgb {
  const amount = (at - lower.at) / (upper.at - lower.at)
  return {
    red: Math.round(lerp(lower.colour.red, upper.colour.red, amount)),
    green: Math.round(lerp(lower.colour.green, upper.colour.green, amount)),
    blue: Math.round(lerp(lower.colour.blue, upper.colour.blue, amount)),
  }
}

/** The disk's colour at a point between its inner edge (0) and outer edge (1). */
export function diskColour(position: number): Rgb {
  const at = clamp(position, 0, 1)
  let lower = INNER_EDGE_STOP
  for (const upper of MIDDLE_STOPS) {
    if (at <= upper.at) {
      return mixStops(lower, upper, at)
    }
    lower = upper
  }
  return mixStops(lower, OUTER_EDGE_STOP, at)
}

/** A point's share of the way from the disk's inner edge to its outer edge. */
function diskPosition(radius: number): number {
  return (radius - DISK_INNER_RADIUS) / (DISK_OUTER_RADIUS - DISK_INNER_RADIUS)
}

/** Angular speed at a radius: Kepler's third law gives speed ∝ r^-1.5. */
export function orbitalSpeed(radius: number): number {
  return BASE_ORBITAL_SPEED * radius ** -1.5
}

/** Where a particle is round the disk after `diskTime` seconds. */
export function particleAngle(particle: DiskParticle, diskTime: number): number {
  return particle.startAngle + particle.angularSpeed * diskTime
}

function roundDown(value: number, step: number): number {
  return Math.floor(value / step) * step
}

function createParticle(random: () => number): DiskParticle {
  // Raising the random number to a power above 1 crowds particles towards the bright inner edge.
  const radius = lerp(DISK_INNER_RADIUS, DISK_OUTER_RADIUS, random() ** 1.8)
  const position = diskPosition(radius)
  const { red, green, blue } = diskColour(roundDown(position, 1 / COLOUR_BANDS))
  // Bright near the centre, fading to a faint haze at the outer edge.
  const brightness = 0.72 * (1 - position) ** 1.4 * (0.5 + random() * 0.5)
  const alpha = 0.08 + roundDown(brightness, ALPHA_STEP)
  // A little jitter in speed makes neighbouring particles drift apart: the swirl.
  const speedJitter = 0.9 + random() * 0.2

  return {
    radius,
    startAngle: random() * Math.PI * 2,
    angularSpeed: orbitalSpeed(radius) * speedJitter,
    length: (0.04 + random() * 0.12) * Math.sqrt(DISK_INNER_RADIUS / radius),
    colour: `rgba(${red}, ${green}, ${blue}, ${alpha.toFixed(3)})`,
  }
}

function createStar(random: () => number): Star {
  return {
    x: random(),
    y: random(),
    size: 0.4 + random(),
    alpha: 0.15 + random() * 0.7,
    depth: 0.2 + random() * 0.8,
  }
}

function groupByColour(particles: DiskParticle[]): ParticleBatch[] {
  const batchesByColour = new Map<string, ParticleBatch>()
  for (const particle of particles) {
    const batch = batchesByColour.get(particle.colour)
    if (batch === undefined) {
      batchesByColour.set(particle.colour, { colour: particle.colour, particles: [particle] })
    } else {
      batch.particles.push(particle)
    }
  }
  return [...batchesByColour.values()]
}

/** Every particle and star in the hero, built once from a seed. */
export function createScene(seed: number): Scene {
  const random = createRandom(seed)
  const particles: DiskParticle[] = []
  for (let count = 0; count < PARTICLE_COUNT; count += 1) {
    particles.push(createParticle(random))
  }
  const stars: Star[] = []
  for (let count = 0; count < STAR_COUNT; count += 1) {
    stars.push(createStar(random))
  }
  return { batches: groupByColour(particles), stars }
}

/** The camera for a scroll progress between 0 (top of the hero) and 1 (past it). */
export function viewAt(progress: number): View {
  const eased = easeInOutCubic(clamp(progress, 0, 1))
  return {
    tilt: lerp(TILT_AT_TOP, TILT_AT_BOTTOM, eased),
    zoom: lerp(ZOOM_AT_TOP, ZOOM_AT_BOTTOM, eased),
    centreHeight: lerp(CENTRE_HEIGHT_AT_TOP, CENTRE_HEIGHT_AT_BOTTOM, eased),
    diskTimeOffset: SCROLL_SWIRL_SECONDS * eased,
    starDrift: STAR_DRIFT_AT_BOTTOM * eased,
  }
}

/** Place a view on a screen: centre it, and size the disk to spill past the edges. */
export function cameraFor(view: View, width: number, height: number): Camera {
  const halfSpan = Math.max(width, height * PORTRAIT_SPAN_FACTOR) / 2
  return {
    centreX: width / 2,
    centreY: height * view.centreHeight,
    scale: ((OUTER_EDGE_SPILL * halfSpan) / DISK_OUTER_RADIUS) * view.zoom,
    tilt: view.tilt,
  }
}

/**
 * A point on the disk, on screen. The disk is a circle seen from just above its plane, so
 * it shows as an ellipse: full width across, squashed by the tilt from front to back.
 */
export function projectOnDisk(radius: number, angle: number, camera: Camera): Point {
  return {
    x: camera.centreX + radius * Math.cos(angle) * camera.scale,
    y: camera.centreY + radius * Math.sin(angle) * camera.scale * camera.tilt,
  }
}

/** The far half of the disk is the half above the centre on screen, behind the hole. */
export function isFarSide(angle: number): boolean {
  return Math.sin(angle) < 0
}

/**
 * Where the black hole's gravity shows a point from the far side of the disk.
 *
 * Light from behind the hole bends over its top, so the far half appears un-squashed: laid
 * out on a circle just outside the shadow instead of on the flat ellipse. That circle is
 * the bright arc over the top of the shadow. Further-out parts of the disk land further out
 * on the arc.
 */
export function lensedPoint(radius: number, angle: number, camera: Camera): Point {
  const reach = clamp(
    (radius - DISK_INNER_RADIUS) / (LENSED_OUTER_RADIUS - DISK_INNER_RADIUS),
    0,
    1,
  )
  const arcRadius = SHADOW_RADIUS * lerp(LENSED_ARC_INNER, LENSED_ARC_OUTER, reach)
  return {
    x: camera.centreX + arcRadius * Math.cos(angle) * camera.scale,
    y: camera.centreY + arcRadius * Math.sin(angle) * camera.scale,
  }
}

/** True for a point bright enough, and far enough behind the hole, to show in the arc. */
export function isLensed(radius: number, angle: number): boolean {
  return radius <= LENSED_OUTER_RADIUS && Math.sin(angle) < -LENSED_MIN_DEPTH
}

/** A star on screen. Nearer stars drift further, and a star that drifts off the top wraps
 *  round to the bottom, so the sky never runs out. */
export function starPosition(star: Star, drift: number, width: number, height: number): Point {
  const shifted = star.y - drift * star.depth
  const wrapped = shifted - Math.floor(shifted)
  return { x: star.x * width, y: wrapped * height }
}
