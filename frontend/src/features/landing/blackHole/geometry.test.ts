import {
  cameraFor,
  createRandom,
  createScene,
  DISK_INNER_RADIUS,
  DISK_OUTER_RADIUS,
  diskColour,
  isFarSide,
  isLensed,
  lensedPoint,
  orbitalSpeed,
  particleAngle,
  projectOnDisk,
  SHADOW_RADIUS,
  starPosition,
  viewAt,
} from './geometry'

const DESKTOP = { width: 1440, height: 900 }
const MOBILE = { width: 390, height: 844 }
const CAMERA = { centreX: 500, centreY: 400, scale: 100, tilt: 0.2 }

describe('createRandom', () => {
  it('gives the same numbers for the same seed, all in [0, 1)', () => {
    const first = createRandom(42)
    const second = createRandom(42)

    for (let draw = 0; draw < 100; draw += 1) {
      const value = first()
      expect(value).toBe(second())
      expect(value).toBeGreaterThanOrEqual(0)
      expect(value).toBeLessThan(1)
    }
  })

  it('gives different numbers for different seeds', () => {
    expect(createRandom(1)()).not.toBe(createRandom(2)())
  })
})

describe('createScene', () => {
  it('builds the same disk and sky from the same seed', () => {
    expect(createScene(7)).toEqual(createScene(7))
  })

  it('keeps every particle between the inner and outer edge of the disk', () => {
    const particles = createScene(7).batches.flatMap((batch) => batch.particles)

    expect(particles.length).toBeGreaterThan(1000)
    for (const particle of particles) {
      expect(particle.radius).toBeGreaterThanOrEqual(DISK_INNER_RADIUS)
      expect(particle.radius).toBeLessThanOrEqual(DISK_OUTER_RADIUS)
    }
  })

  it('groups particles by colour, so each colour is drawn in one stroke', () => {
    const { batches } = createScene(7)
    const colours = batches.map((batch) => batch.colour)

    expect(new Set(colours).size).toBe(batches.length)
    expect(batches.length).toBeLessThan(200)
    for (const batch of batches) {
      for (const particle of batch.particles) {
        expect(particle.colour).toBe(batch.colour)
      }
    }
  })

  it('places every star inside the sky', () => {
    const { stars } = createScene(7)

    expect(stars.length).toBeGreaterThan(100)
    for (const star of stars) {
      expect(star.x).toBeGreaterThanOrEqual(0)
      expect(star.x).toBeLessThan(1)
      expect(star.y).toBeGreaterThanOrEqual(0)
      expect(star.y).toBeLessThan(1)
    }
  })
})

describe('orbitalSpeed', () => {
  it('follows Kepler: eight times faster at a quarter of the distance', () => {
    expect(orbitalSpeed(1) / orbitalSpeed(4)).toBeCloseTo(8)
  })

  it('moves a particle on by its speed over time', () => {
    const particle = { radius: 2, startAngle: 1, angularSpeed: 0.5, length: 0.1, colour: '' }

    expect(particleAngle(particle, 4)).toBeCloseTo(3)
  })
})

describe('diskColour', () => {
  it('is hot cream at the inner edge and violet at the outer edge', () => {
    expect(diskColour(0)).toEqual({ red: 255, green: 241, blue: 214 })
    expect(diskColour(1)).toEqual({ red: 58, green: 29, blue: 92 })
  })

  it('passes through orange on the way out', () => {
    const middle = diskColour(0.35)

    expect(middle.red).toBe(255)
    expect(middle.green).toBeLessThan(170)
    expect(middle.blue).toBeLessThan(80)
  })

  it('treats positions past either edge as the edge', () => {
    expect(diskColour(-1)).toEqual(diskColour(0))
    expect(diskColour(2)).toEqual(diskColour(1))
  })
})

describe('projectOnDisk', () => {
  it('puts angle 0 straight out to the right of the centre', () => {
    const point = projectOnDisk(3, 0, CAMERA)

    expect(point.x).toBeCloseTo(800)
    expect(point.y).toBeCloseTo(400)
  })

  it('squashes the disk by the tilt: the near side sits just below the centre', () => {
    const point = projectOnDisk(3, Math.PI / 2, CAMERA)

    expect(point.x).toBeCloseTo(500)
    expect(point.y).toBeCloseTo(400 + 3 * 100 * 0.2)
  })
})

describe('isFarSide', () => {
  it('is the half of the disk above the centre, behind the black hole', () => {
    expect(isFarSide((3 * Math.PI) / 2)).toBe(true)
    expect(isFarSide(Math.PI / 2)).toBe(false)
  })
})

describe('lensedPoint', () => {
  it('bends the far side up over the top of the shadow', () => {
    const behindTheHole = lensedPoint(DISK_INNER_RADIUS, (3 * Math.PI) / 2, CAMERA)
    const shadowTop = CAMERA.centreY - SHADOW_RADIUS * CAMERA.scale

    expect(behindTheHole.x).toBeCloseTo(CAMERA.centreX)
    expect(behindTheHole.y).toBeLessThan(shadowTop)
  })

  it('lifts outer parts of the disk higher than inner parts', () => {
    const inner = lensedPoint(DISK_INNER_RADIUS, (3 * Math.PI) / 2, CAMERA)
    const outer = lensedPoint(DISK_INNER_RADIUS + 1, (3 * Math.PI) / 2, CAMERA)

    expect(outer.y).toBeLessThan(inner.y)
  })
})

describe('isLensed', () => {
  const BEHIND = (3 * Math.PI) / 2

  it('shows only the bright inner disk in the lensed arc, not the faint outer haze', () => {
    expect(isLensed(DISK_INNER_RADIUS, BEHIND)).toBe(true)
    expect(isLensed(DISK_OUTER_RADIUS, BEHIND)).toBe(false)
  })

  it('leaves out points near the sides and on the near side', () => {
    expect(isLensed(DISK_INNER_RADIUS, Math.PI + 0.1)).toBe(false)
    expect(isLensed(DISK_INNER_RADIUS, Math.PI / 2)).toBe(false)
  })
})

describe('viewAt', () => {
  it('starts nearly edge-on and close, and ends more open and further back', () => {
    const top = viewAt(0)
    const bottom = viewAt(1)

    expect(bottom.tilt).toBeGreaterThan(top.tilt)
    expect(bottom.zoom).toBeLessThan(top.zoom)
    expect(bottom.diskTimeOffset).toBeGreaterThan(top.diskTimeOffset)
    expect(bottom.starDrift).toBeGreaterThan(top.starDrift)
  })

  it('treats progress outside 0 to 1 as the nearest end', () => {
    expect(viewAt(-0.5)).toEqual(viewAt(0))
    expect(viewAt(3)).toEqual(viewAt(1))
  })

  it('opens the tilt steadily as the page scrolls', () => {
    expect(viewAt(0.25).tilt).toBeLessThan(viewAt(0.5).tilt)
    expect(viewAt(0.5).tilt).toBeLessThan(viewAt(0.75).tilt)
  })
})

describe('cameraFor', () => {
  it.each([
    ['desktop', DESKTOP],
    ['mobile', MOBILE],
  ])('zooms in so the disk spills past both edges on %s', (_label, size) => {
    const camera = cameraFor(viewAt(0), size.width, size.height)

    expect(camera.centreX).toBe(size.width / 2)
    expect(DISK_OUTER_RADIUS * camera.scale).toBeGreaterThan(size.width / 2)
  })

  it('pulls back as the view zooms out', () => {
    const start = cameraFor(viewAt(0), DESKTOP.width, DESKTOP.height)
    const end = cameraFor(viewAt(1), DESKTOP.width, DESKTOP.height)

    expect(end.scale).toBeLessThan(start.scale)
    expect(end.tilt).toBe(viewAt(1).tilt)
  })
})

describe('starPosition', () => {
  const star = { x: 0.5, y: 0.5, size: 1, alpha: 1, depth: 1 }

  it('places a star by its share of the sky', () => {
    expect(starPosition(star, 0, 1000, 800)).toEqual({ x: 500, y: 400 })
  })

  it('drifts nearer stars further, and wraps them round to the bottom', () => {
    const near = starPosition(star, 0.25, 1000, 800)
    const far = starPosition({ ...star, depth: 0.2 }, 0.25, 1000, 800)
    const wrapped = starPosition({ ...star, y: 0.1 }, 0.25, 1000, 800)

    expect(near.y).toBeCloseTo(200)
    expect(far.y).toBeCloseTo(360)
    expect(wrapped.y).toBeCloseTo(680)
  })
})
