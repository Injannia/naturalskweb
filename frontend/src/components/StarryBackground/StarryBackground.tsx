import { useRef, useEffect } from 'react'

interface Star {
  x: number
  y: number
  size: number
  opacity: number
  twinkleSpeed: number
  twinklePhase: number
}

interface ShootingStar {
  x: number
  y: number
  length: number
  speed: number
  angle: number
  opacity: number
  life: number
  maxLife: number
}

export default function StarryBackground() {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    const ctx = canvas.getContext('2d')
    if (!ctx) return

    let animationId: number
    let stars: Star[] = []
    let shootingStars: ShootingStar[] = []

    function resize() {
      canvas!.width = window.innerWidth
      canvas!.height = window.innerHeight
      initStars()
    }

    function initStars() {
      const count = Math.min(
        400,
        Math.max(200, Math.floor((canvas!.width * canvas!.height) / 5000)),
      )
      stars = Array.from({ length: count }, () => ({
        x: Math.random() * canvas!.width,
        y: Math.random() * canvas!.height,
        size: Math.random() * 2 + 0.5,
        opacity: Math.random() * 0.8 + 0.2,
        twinkleSpeed: Math.random() * 0.02 + 0.005,
        twinklePhase: Math.random() * Math.PI * 2,
      }))
    }

    function spawnShootingStar() {
      if (shootingStars.length >= 2) return
      shootingStars.push({
        x: Math.random() * canvas!.width * 0.8,
        y: Math.random() * canvas!.height * 0.3,
        length: Math.random() * 60 + 40,
        speed: Math.random() * 6 + 4,
        angle: (Math.random() * 0.4 + 0.3) * Math.PI,
        opacity: 1,
        life: 0,
        maxLife: Math.random() * 40 + 30,
      })
    }

    let time = 0

    function draw() {
      ctx!.clearRect(0, 0, canvas!.width, canvas!.height)
      time++

      // Stars
      for (const star of stars) {
        const twinkle =
          Math.sin(time * star.twinkleSpeed + star.twinklePhase) * 0.3 + 0.7
        const alpha = star.opacity * twinkle

        ctx!.beginPath()
        ctx!.arc(star.x, star.y, star.size, 0, Math.PI * 2)
        ctx!.fillStyle = `rgba(255, 255, 255, ${alpha})`
        ctx!.fill()

        if (star.size > 1.5) {
          ctx!.beginPath()
          ctx!.arc(star.x, star.y, star.size * 2.5, 0, Math.PI * 2)
          ctx!.fillStyle = `rgba(110, 123, 255, ${alpha * 0.08})`
          ctx!.fill()
        }
      }

      // Shooting stars
      for (let i = shootingStars.length - 1; i >= 0; i--) {
        const ss = shootingStars[i]
        ss.life++
        ss.x += Math.cos(ss.angle) * ss.speed
        ss.y += Math.sin(ss.angle) * ss.speed
        ss.opacity = 1 - ss.life / ss.maxLife

        if (ss.life >= ss.maxLife) {
          shootingStars.splice(i, 1)
          continue
        }

        const tailX = ss.x - Math.cos(ss.angle) * ss.length
        const tailY = ss.y - Math.sin(ss.angle) * ss.length

        const gradient = ctx!.createLinearGradient(tailX, tailY, ss.x, ss.y)
        gradient.addColorStop(0, `rgba(255, 255, 255, 0)`)
        gradient.addColorStop(1, `rgba(255, 255, 255, ${ss.opacity})`)

        ctx!.beginPath()
        ctx!.moveTo(tailX, tailY)
        ctx!.lineTo(ss.x, ss.y)
        ctx!.strokeStyle = gradient
        ctx!.lineWidth = 1.5
        ctx!.stroke()

        ctx!.beginPath()
        ctx!.arc(ss.x, ss.y, 2, 0, Math.PI * 2)
        ctx!.fillStyle = `rgba(255, 255, 255, ${ss.opacity})`
        ctx!.fill()
      }

      // Random shooting star spawn
      if (Math.random() < 0.003) {
        spawnShootingStar()
      }

      animationId = requestAnimationFrame(draw)
    }

    resize()
    draw()

    window.addEventListener('resize', resize)
    return () => {
      window.removeEventListener('resize', resize)
      cancelAnimationFrame(animationId)
    }
  }, [])

  return (
    <canvas
      ref={canvasRef}
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        width: '100%',
        height: '100%',
        zIndex: 0,
        pointerEvents: 'none',
        willChange: 'transform',
      }}
    />
  )
}
