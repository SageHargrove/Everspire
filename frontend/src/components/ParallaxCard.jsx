import React, { useEffect, useRef } from 'react'

/**
 * Tilt-on-pointer depth for card art.
 *
 * Publishes two unitless CSS variables on its own node — `--px` and `--py`,
 * each in [-1, 1] — and lets CSS do the rest. Nothing here re-renders React
 * while the pointer moves, which matters: the hero grid shows 24 of these at
 * once and a setState per mousemove would be a stutter machine.
 *
 * Children opt into depth by carrying `.parallax-layer` with a `--depth`
 * (in px of travel at full deflection). Displacement stays small on purpose —
 * nobody has ever complained that a card's parallax was too subtle, they
 * complain when it warps.
 */

const MOTION_QUERY = '(prefers-reduced-motion: reduce)'

function motionAllowed() {
  if (typeof window === 'undefined' || !window.matchMedia) return true
  return !window.matchMedia(MOTION_QUERY).matches
}

/* ---------------------------------------------------------------------------
 * Device orientation, shared.
 *
 * One window listener for the whole page rather than one per card: on a phone
 * every visible card reacts to the same tilt, so 24 identical listeners would
 * be 24x the work for the same numbers. Cards subscribe and unsubscribe; the
 * listener attaches on the first subscriber and detaches on the last.
 *
 * iOS needs DeviceOrientationEvent.requestPermission() from inside a user
 * gesture, which a card can't ask for. Rather than nag, this just never fires
 * there and the cards sit flat — the desktop pointer path is the real one.
 * ------------------------------------------------------------------------- */
const orientSubs = new Set()
let orientAttached = false

function handleOrientation(e) {
  // gamma is left/right tilt, beta is front/back. +-25 degrees covers a
  // comfortable wrist range; past that it clamps rather than pinning.
  const x = Math.max(-1, Math.min(1, (e.gamma || 0) / 25))
  // Phones are held tilted back, so beta rests near 45 rather than 0.
  const y = Math.max(-1, Math.min(1, ((e.beta || 0) - 45) / 25))
  orientSubs.forEach(fn => fn(x, y))
}

function subscribeOrientation(fn) {
  if (typeof window === 'undefined' || !('DeviceOrientationEvent' in window)) return () => {}
  orientSubs.add(fn)
  if (!orientAttached) {
    window.addEventListener('deviceorientation', handleOrientation, { passive: true })
    orientAttached = true
  }
  return () => {
    orientSubs.delete(fn)
    if (orientSubs.size === 0 && orientAttached) {
      window.removeEventListener('deviceorientation', handleOrientation)
      orientAttached = false
    }
  }
}

export default function ParallaxCard({
  children,
  className = '',
  style,
  maxTilt = 7,
  glare = true,
  disabled = false,
  ...rest
}) {
  const ref = useRef(null)

  useEffect(() => {
    const el = ref.current
    if (!el || disabled) return

    let raf = 0
    let px = 0
    let py = 0
    // Cached on enter rather than measured per move: getBoundingClientRect
    // forces layout, and doing that every mousemove over a grid of cards is
    // exactly the kind of thing that turns a nice effect into jank.
    let rect = null

    const flush = () => {
      raf = 0
      el.style.setProperty('--px', px.toFixed(4))
      el.style.setProperty('--py', py.toFixed(4))
    }
    const schedule = () => { if (!raf) raf = requestAnimationFrame(flush) }

    const set = (x, y) => {
      px = x
      py = y
      schedule()
    }

    // Touch and pen are handled by the orientation path instead: a finger is
    // ON the card, so tracking it would put the hand over the art it's
    // supposed to be showing off.
    const onEnter = (e) => {
      if (e.pointerType !== 'mouse' || !motionAllowed()) return
      rect = el.getBoundingClientRect()
      el.classList.add('parallax-active')
    }
    const onMove = (e) => {
      if (!rect || e.pointerType !== 'mouse' || !motionAllowed()) return
      set(
        Math.max(-1, Math.min(1, ((e.clientX - rect.left) / rect.width) * 2 - 1)),
        Math.max(-1, Math.min(1, ((e.clientY - rect.top) / rect.height) * 2 - 1)),
      )
    }
    const onLeave = () => {
      el.classList.remove('parallax-active')
      rect = null
      set(0, 0)          // eases home via the slower resting transition
    }
    // The roster is a scrolling grid, and a wheel scroll under a hovered card
    // moves the card without moving the pointer — leaving the cached rect
    // describing where the card used to be, and the tilt mapped to the wrong
    // spot. Re-measure on the next move instead of on every frame.
    const onScroll = () => { if (rect) rect = el.getBoundingClientRect() }

    el.addEventListener('pointerenter', onEnter)
    el.addEventListener('pointermove', onMove)
    el.addEventListener('pointerleave', onLeave)
    window.addEventListener('scroll', onScroll, { passive: true, capture: true })

    let unsubOrient = () => {}
    if (window.matchMedia?.('(pointer: coarse)').matches) {
      unsubOrient = subscribeOrientation((x, y) => {
        if (!motionAllowed()) return
        el.classList.add('parallax-active')
        set(x, y)
      })
    }

    return () => {
      if (raf) cancelAnimationFrame(raf)
      el.removeEventListener('pointerenter', onEnter)
      el.removeEventListener('pointermove', onMove)
      el.removeEventListener('pointerleave', onLeave)
      window.removeEventListener('scroll', onScroll, { capture: true })
      unsubOrient()
    }
  }, [disabled])

  if (disabled) {
    return <div className={className} style={style} {...rest}>{children}</div>
  }

  return (
    <div
      ref={ref}
      className={`parallax ${className}`}
      style={{ ...style, '--tilt': `${maxTilt}deg` }}
      {...rest}
    >
      <div className="parallax-inner">
        {children}
        {glare && <div className="parallax-glare" aria-hidden="true" />}
      </div>
    </div>
  )
}
