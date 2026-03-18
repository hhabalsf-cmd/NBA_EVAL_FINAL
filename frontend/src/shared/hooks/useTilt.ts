import { useRef, useCallback, useMemo } from 'react'
import { useMotionValue, useSpring, useTransform, type MotionStyle } from 'framer-motion'

interface UseTiltOptions {
  maxTilt?: number
  scale?: number
  springConfig?: { stiffness: number; damping: number }
}

export function useTilt({
  maxTilt = 8,
  scale = 1.02,
  springConfig = { stiffness: 260, damping: 20 },
}: UseTiltOptions = {}) {
  const ref = useRef<HTMLDivElement>(null)

  const x = useMotionValue(0)
  const y = useMotionValue(0)
  const s = useMotionValue(1)

  const springX = useSpring(x, springConfig)
  const springY = useSpring(y, springConfig)
  const springS = useSpring(s, springConfig)

  const rotateX = useTransform(springY, [-0.5, 0.5], [maxTilt, -maxTilt])
  const rotateY = useTransform(springX, [-0.5, 0.5], [-maxTilt, maxTilt])

  const onMouseMove = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      const el = ref.current
      if (!el) return
      const rect = el.getBoundingClientRect()
      const px = (e.clientX - rect.left) / rect.width - 0.5
      const py = (e.clientY - rect.top) / rect.height - 0.5
      x.set(px)
      y.set(py)
    },
    [x, y],
  )

  const onMouseEnter = useCallback(() => {
    s.set(scale)
  }, [s, scale])

  const onMouseLeave = useCallback(() => {
    x.set(0)
    y.set(0)
    s.set(1)
  }, [x, y, s])

  const style = useMemo<MotionStyle>(
    () => ({
      rotateX: rotateX,
      rotateY: rotateY,
      scale: springS,
      transformPerspective: 800,
    }),
    [rotateX, rotateY, springS],
  )

  return { ref, style, onMouseMove, onMouseEnter, onMouseLeave }
}
