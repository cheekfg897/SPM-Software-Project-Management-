/**
 * Paints the black hole onto a 2D canvas, one frame at a time.
 *
 * All the maths lives in geometry.ts; this file only turns its numbers into paint, layer by
 * layer, back to front:
 *
 *   1. space and stars
 *   2. the glow round the disk, and the far half of the disk (behind the hole)
 *   3. the shadow, which hides the middle of the far half
 *   4. the lensed arc and the photon ring over the top of the shadow
 *   5. the near half of the disk, which passes in front of the shadow
 *
 * Light layers are added together ('lighter'), as light is, so where they overlap they burn
 * towards white, like the inside of a real accretion disk.
 */

/* v8 ignore start -- jsdom has no 2D canvas, so nothing here can run in unit tests; the e2e tests sample these pixels in a real browser */

import type { Camera, DiskParticle, ParticleBatch, Point, Scene } from './geometry'
import {
  cameraFor,
  DISK_INNER_RADIUS,
  DISK_OUTER_RADIUS,
  diskColour,
  isFarSide,
  isLensed,
  LENSED_ARC_INNER,
  LENSED_ARC_OUTER,
  lensedPoint,
  particleAngle,
  projectOnDisk,
  SHADOW_RADIUS,
  starPosition,
  viewAt,
} from './geometry'

// Canvas can't read Tailwind classes, so the colours it paints with are named here.
// SPACE_COLOUR matches --color-void in src/index.css; CORONA, FLARE, EMBER and NEBULA match
// the tokens of the same names. The disk's own colours come from diskColour in geometry.ts.
const SPACE_COLOUR = '#06050b'
const SHADOW_CORE_COLOUR = '#000000'
const STARLIGHT_RGB = '255, 248, 235'
const CORONA_RGB = '255, 241, 214'
const FLARE_RGB = '255, 154, 60'
const EMBER_RGB = '224, 69, 43'
const NEBULA_RGB = '138, 77, 189'

/** Sharper than 2x costs more than it shows on a moving scene. */
const MAX_PIXEL_RATIO = 2

const STREAK_WIDTH = 1.1

/** The lensed arc is drawn as this many thin bands, bright inside to dim outside. */
const LENSED_ARC_BANDS = 14
/**
 * How bright the arc and ring are round the top half, as a share of their brightest: full
 * over the top, still most of it a little way from the sides, and nothing where they meet
 * the disk, so they never end in a hard edge. `at` runs clockwise from the left end (0)
 * over the top (0.25) to the right end (0.5), as the conic gradient does.
 */
const ARC_BRIGHTNESS_STOPS = [
  { at: 0, share: 0 },
  { at: 0.07, share: 0.6 },
  { at: 0.25, share: 1 },
  { at: 0.43, share: 0.6 },
  { at: 0.5, share: 0 },
]
const TWINKLE_SPEED = 1.3

export interface Frame {
  /** CSS pixels. */
  width: number
  height: number
  /** Scroll progress through the hero, 0 to 1. */
  progress: number
  /** Time since the page opened, which drives the orbit and the twinkle. */
  seconds: number
}

type Half = 'far' | 'near'
type Placement = (radius: number, angle: number, camera: Camera) => Point
type Filter = (particle: DiskParticle, angle: number) => boolean

function rgba(rgb: string, alpha: number): string {
  return `rgba(${rgb}, ${alpha.toFixed(3)})`
}

/** The disk's smooth body: its colour at each point out from the inner edge, fading out. */
function diskBodyStops(): { at: number; colour: string }[] {
  const positions = [0, 0.04, 0.12, 0.25, 0.4, 0.6, 0.8, 1]
  return positions.map((at) => {
    const { red, green, blue } = diskColour(at)
    const alpha = 0.04 + 0.92 * (1 - at) ** 1.15
    return { at, colour: rgba(`${red}, ${green}, ${blue}`, alpha) }
  })
}

const DISK_BODY_STOPS = diskBodyStops()

/** The angles each half of the disk covers. The far half is above the centre on screen. */
function halfAngles(half: Half): { start: number; end: number } {
  return half === 'far' ? { start: Math.PI, end: Math.PI * 2 } : { start: 0, end: Math.PI }
}

/** A ring between two radii round the origin, over the angles given, as the current path. */
function traceRing(
  context: CanvasRenderingContext2D,
  innerRadius: number,
  outerRadius: number,
  start: number,
  end: number,
): void {
  context.beginPath()
  context.arc(0, 0, outerRadius, start, end)
  context.arc(0, 0, innerRadius, end, start, true)
  context.closePath()
}

function paintSpace(context: CanvasRenderingContext2D, frame: Frame): void {
  context.fillStyle = SPACE_COLOUR
  context.fillRect(0, 0, frame.width, frame.height)
}

function paintStars(
  context: CanvasRenderingContext2D,
  scene: Scene,
  frame: Frame,
  drift: number,
): void {
  for (const star of scene.stars) {
    const { x, y } = starPosition(star, drift, frame.width, frame.height)
    // Each star twinkles on its own beat, set by where it sits.
    const twinkle = 0.7 + 0.3 * Math.sin(frame.seconds * TWINKLE_SPEED + star.x * 40)
    context.fillStyle = rgba(STARLIGHT_RGB, star.alpha * twinkle)
    context.fillRect(x, y, star.size, star.size)
  }
}

/** A wide, soft glow round the whole disk: the violet haze at the edges of the image. */
function paintHaze(context: CanvasRenderingContext2D, camera: Camera): void {
  const reach = DISK_OUTER_RADIUS * camera.scale * 1.3
  context.save()
  context.translate(camera.centreX, camera.centreY)
  context.scale(1, Math.max(camera.tilt * 2.4, 0.3))
  const glow = context.createRadialGradient(0, 0, 0, 0, 0, reach)
  glow.addColorStop(0, rgba(FLARE_RGB, 0.22))
  glow.addColorStop(0.3, rgba(EMBER_RGB, 0.12))
  glow.addColorStop(0.65, rgba(NEBULA_RGB, 0.07))
  glow.addColorStop(1, rgba(NEBULA_RGB, 0))
  context.fillStyle = glow
  context.fillRect(-reach, -reach, reach * 2, reach * 2)
  context.restore()
}

/**
 * One half of the disk's smooth body. The context is squashed by the tilt, so a round
 * gradient becomes the flat ellipse of a disk seen nearly edge-on.
 */
function paintDiskBody(context: CanvasRenderingContext2D, camera: Camera, half: Half): void {
  const inner = DISK_INNER_RADIUS * camera.scale
  const outer = DISK_OUTER_RADIUS * camera.scale
  const { start, end } = halfAngles(half)

  context.save()
  context.translate(camera.centreX, camera.centreY)
  context.scale(1, camera.tilt)
  const body = context.createRadialGradient(0, 0, inner, 0, 0, outer)
  for (const stop of DISK_BODY_STOPS) {
    body.addColorStop(stop.at, stop.colour)
  }
  context.fillStyle = body
  traceRing(context, inner, outer, start, end)
  context.fill()
  context.restore()
}

/** The white-hot inner edge of one half of the disk. */
function paintInnerEdge(context: CanvasRenderingContext2D, camera: Camera, half: Half): void {
  const radius = DISK_INNER_RADIUS * camera.scale
  const { start, end } = halfAngles(half)
  context.beginPath()
  context.ellipse(camera.centreX, camera.centreY, radius, radius * camera.tilt, 0, start, end)
  context.lineWidth = 2
  context.strokeStyle = rgba(CORONA_RGB, 0.85)
  context.stroke()
}

/**
 * The particles that pass the filter, each drawn as a short streak along its orbit, from
 * where it was a moment ago to where it is now. One stroke per colour batch.
 */
function paintStreaks(
  context: CanvasRenderingContext2D,
  batches: ParticleBatch[],
  camera: Camera,
  diskTime: number,
  shows: Filter,
  place: Placement,
): void {
  context.lineWidth = STREAK_WIDTH
  context.lineCap = 'round'
  for (const batch of batches) {
    context.strokeStyle = batch.colour
    context.beginPath()
    for (const particle of batch.particles) {
      const angle = particleAngle(particle, diskTime)
      if (!shows(particle, angle)) {
        continue
      }
      const tail = place(particle.radius, angle - particle.length, camera)
      const head = place(particle.radius, angle, camera)
      context.moveTo(tail.x, tail.y)
      context.lineTo(head.x, head.y)
    }
    context.stroke()
  }
}

/**
 * The event horizon's shadow: black, with no light of its own. Its top half is round; below
 * the middle only a thin sliver shows before the near side of the disk passes in front, so
 * the lower half is squashed like the disk. That gives the dome over a flat brim.
 */
function paintShadow(context: CanvasRenderingContext2D, camera: Camera): void {
  const radius = SHADOW_RADIUS * camera.scale
  const { centreX, centreY } = camera
  const shade = context.createRadialGradient(centreX, centreY, 0, centreX, centreY, radius)
  shade.addColorStop(0, SHADOW_CORE_COLOUR)
  shade.addColorStop(1, SPACE_COLOUR)
  context.fillStyle = shade
  context.beginPath()
  context.arc(centreX, centreY, radius, Math.PI, Math.PI * 2)
  context.ellipse(centreX, centreY, radius, radius * camera.tilt, 0, 0, Math.PI)
  context.fill()
}

/**
 * A stroke style for the top half of a ring that is brightest over the top and fades out
 * towards the sides (ARC_BRIGHTNESS_STOPS). The conic gradient starts at the left (angle π).
 */
function fadingArcStyle(
  context: CanvasRenderingContext2D,
  camera: Camera,
  rgb: string,
  alpha: number,
): CanvasGradient {
  const style = context.createConicGradient(Math.PI, camera.centreX, camera.centreY)
  for (const stop of ARC_BRIGHTNESS_STOPS) {
    style.addColorStop(stop.at, rgba(rgb, alpha * stop.share))
  }
  return style
}

/** The top half of a ring round the hole, `radius` and `width` in shadow radii. */
function strokeArcBand(
  context: CanvasRenderingContext2D,
  camera: Camera,
  band: { radius: number; width: number; rgb: string; alpha: number },
): void {
  context.beginPath()
  context.arc(
    camera.centreX,
    camera.centreY,
    band.radius * SHADOW_RADIUS * camera.scale,
    Math.PI,
    Math.PI * 2,
  )
  context.lineWidth = Math.max(band.width * camera.scale, 1)
  context.strokeStyle = fadingArcStyle(context, camera, band.rgb, band.alpha)
  context.stroke()
}

/**
 * The far side of the disk, bent up over the top of the shadow by the hole's gravity: thin
 * bands from just outside the shadow outwards, hot and bright inside, dimmer and redder out.
 */
function paintLensedArc(context: CanvasRenderingContext2D, camera: Camera): void {
  const outerEdge = LENSED_ARC_OUTER * 1.15
  const bandWidth = (outerEdge - LENSED_ARC_INNER) / LENSED_ARC_BANDS
  for (let band = 0; band < LENSED_ARC_BANDS; band += 1) {
    const outward = band / (LENSED_ARC_BANDS - 1)
    const { red, green, blue } = diskColour(outward * 0.6)
    strokeArcBand(context, camera, {
      radius: LENSED_ARC_INNER + bandWidth * (band + 0.5),
      width: bandWidth * 1.1,
      rgb: `${red}, ${green}, ${blue}`,
      alpha: 0.95 * (1 - outward) ** 1.25,
    })
  }
}

/** The thin, bright ring of light orbiting right at the edge of the shadow, and its glow. */
function paintPhotonRing(context: CanvasRenderingContext2D, camera: Camera): void {
  strokeArcBand(context, camera, { radius: 1.06, width: 0.1, rgb: FLARE_RGB, alpha: 0.5 })
  strokeArcBand(context, camera, { radius: 1.012, width: 0.012, rgb: CORONA_RGB, alpha: 1 })
}

const onFarSide: Filter = (_particle, angle) => isFarSide(angle)
const onNearSide: Filter = (_particle, angle) => !isFarSide(angle)
const onLensedSide: Filter = (particle, angle) => isLensed(particle.radius, angle)

/** Size the canvas's pixels to its size on screen, sharp on high-density displays. */
export function fitCanvas(canvas: HTMLCanvasElement, context: CanvasRenderingContext2D): void {
  const pixelRatio = Math.min(window.devicePixelRatio || 1, MAX_PIXEL_RATIO)
  canvas.width = Math.round(canvas.clientWidth * pixelRatio)
  canvas.height = Math.round(canvas.clientHeight * pixelRatio)
  context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0)
}

/** Paint one frame of the black hole. */
export function drawScene(context: CanvasRenderingContext2D, scene: Scene, frame: Frame): void {
  const view = viewAt(frame.progress)
  const camera = cameraFor(view, frame.width, frame.height)
  const diskTime = frame.seconds + view.diskTimeOffset

  context.globalCompositeOperation = 'source-over'
  paintSpace(context, frame)
  paintStars(context, scene, frame, view.starDrift)

  context.globalCompositeOperation = 'lighter'
  paintHaze(context, camera)
  paintDiskBody(context, camera, 'far')
  paintInnerEdge(context, camera, 'far')
  paintStreaks(context, scene.batches, camera, diskTime, onFarSide, projectOnDisk)

  context.globalCompositeOperation = 'source-over'
  paintShadow(context, camera)

  context.globalCompositeOperation = 'lighter'
  paintLensedArc(context, camera)
  paintStreaks(context, scene.batches, camera, diskTime, onLensedSide, lensedPoint)
  paintPhotonRing(context, camera)

  paintDiskBody(context, camera, 'near')
  paintInnerEdge(context, camera, 'near')
  paintStreaks(context, scene.batches, camera, diskTime, onNearSide, projectOnDisk)

  context.globalCompositeOperation = 'source-over'
}

/* v8 ignore stop */
