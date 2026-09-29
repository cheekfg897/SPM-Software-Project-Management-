import { useEffect, useRef } from 'react'

import { createScene } from '../blackHole/geometry'
import { drawScene, fitCanvas } from '../blackHole/renderer'
import { usePrefersReducedMotion } from '../hooks/usePrefersReducedMotion'

/** Any fixed number will do: the same seed draws the same disk and sky on every visit. */
const SCENE_SEED = 20261004

/** True while any part of the canvas is on screen; no point painting it otherwise. */
function isOnScreen(canvas: HTMLCanvasElement): boolean {
  const { top, bottom } = canvas.getBoundingClientRect()
  return bottom > 0 && top < window.innerHeight
}

interface BlackHoleCanvasProps {
  /** Scroll progress through the hero, 0 to 1. */
  progress: number
}

/**
 * The black hole, animated. It keeps orbiting on its own and moves with `progress`. With
 * reduced motion it paints one still frame instead. Purely decorative.
 */
export function BlackHoleCanvas({ progress }: BlackHoleCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  // Read by the animation loop, so scrolling doesn't restart the loop on every change.
  const progressRef = useRef(progress)
  const prefersReducedMotion = usePrefersReducedMotion()

  useEffect(() => {
    progressRef.current = progress
  }, [progress])

  useEffect(() => {
    const canvas = canvasRef.current
    const context = canvas?.getContext('2d')
    // No 2D canvas (jsdom, or a browser that refuses one): the hero reads fine without it.
    if (!canvas || !context) {
      return
    }

    const scene = createScene(SCENE_SEED)
    const fit = () => fitCanvas(canvas, context)
    const drawAt = (seconds: number) =>
      drawScene(context, scene, {
        width: canvas.clientWidth,
        height: canvas.clientHeight,
        progress: progressRef.current,
        seconds,
      })

    if (prefersReducedMotion) {
      const redrawStill = () => {
        fit()
        drawAt(0)
      }
      redrawStill()
      window.addEventListener('resize', redrawStill)
      return () => window.removeEventListener('resize', redrawStill)
    }

    fit()
    let frameId = 0
    const tick = (now: DOMHighResTimeStamp) => {
      if (isOnScreen(canvas)) {
        drawAt(now / 1000)
      }
      frameId = requestAnimationFrame(tick)
    }
    frameId = requestAnimationFrame(tick)
    window.addEventListener('resize', fit)
    return () => {
      cancelAnimationFrame(frameId)
      window.removeEventListener('resize', fit)
    }
  }, [prefersReducedMotion])

  return <canvas ref={canvasRef} aria-hidden="true" className="absolute inset-0 size-full" />
}
