import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { StrictMode, useState } from 'react'
import { render, screen, act } from '@testing-library/react'

// Mock the axios client used inside useAuthedMedia.
const getMock = vi.fn()
vi.mock('../api/client', () => ({ default: { get: (...a: unknown[]) => getMock(...a) } }))

import { useAuthedMedia } from './useAuthedMedia'

// Track the live set of object URLs so we can assert the displayed src is not revoked.
let live: Set<string>
let counter: number

beforeEach(() => {
  live = new Set()
  counter = 0
  URL.createObjectURL = vi.fn(() => {
    const u = `blob:mock-${counter++}`
    live.add(u)
    return u
  }) as unknown as typeof URL.createObjectURL
  URL.revokeObjectURL = vi.fn((u: string) => {
    live.delete(u)
  }) as unknown as typeof URL.revokeObjectURL
})

afterEach(() => {
  vi.clearAllMocks()
})

function Harness({ url }: { url: string | null }) {
  const src = useAuthedMedia(url)
  return <div data-testid="src" data-src={src ?? ''}>{src}</div>
}

// Parent that re-renders frequently (mirrors MultiDownloaderPage's 1.5s poll
// replacing the tasks array) while the media url for a ready card stays constant.
function PollingParent({ url }: { url: string }) {
  const [, setTick] = useState(0)
  ;(PollingParent as unknown as { bump?: () => void }).bump = () => setTick((t) => t + 1)
  return <Harness url={url} />
}

describe('useAuthedMedia', () => {
  it('keeps the displayed object URL alive after the blob loads (StrictMode)', async () => {
    getMock.mockResolvedValue({ data: new Blob(['x'], { type: 'video/mp4' }) })

    await act(async () => {
      render(
        <StrictMode>
          <Harness url="/multidl/file/abc" />
        </StrictMode>,
      )
    })

    const src = screen.getByTestId('src').getAttribute('data-src')!
    expect(src).toMatch(/^blob:/)
    // The URL handed to <video> must still be registered (not revoked).
    expect(live.has(src)).toBe(true)
  })

  it('keeps the displayed URL alive across parent re-renders with a constant url', async () => {
    getMock.mockResolvedValue({ data: new Blob(['x'], { type: 'video/mp4' }) })

    await act(async () => {
      render(<PollingParent url="/multidl/file/abc" />)
    })

    // Simulate several poll-driven re-renders of the parent.
    for (let i = 0; i < 3; i++) {
      await act(async () => {
        ;(PollingParent as unknown as { bump: () => void }).bump()
      })
    }

    const src = screen.getByTestId('src').getAttribute('data-src')!
    expect(src).toMatch(/^blob:/)
    expect(live.has(src)).toBe(true)
  })

  it('eventually revokes the old URL after the url changes, but only after a grace period', async () => {
    vi.useFakeTimers()
    try {
      getMock.mockResolvedValue({ data: new Blob(['x'], { type: 'video/mp4' }) })

      let rerender: (ui: React.ReactElement) => void = () => {}
      await act(async () => {
        const r = render(<Harness url="/multidl/file/a" />)
        rerender = r.rerender
      })
      const first = screen.getByTestId('src').getAttribute('data-src')!
      expect(live.has(first)).toBe(true)

      await act(async () => {
        rerender(<Harness url="/multidl/file/b" />)
      })
      const second = screen.getByTestId('src').getAttribute('data-src')!
      expect(second).not.toBe(first)
      expect(live.has(second)).toBe(true)
      // Old URL must stay valid immediately after the change so a media element
      // mid-load isn't cut off.
      expect(live.has(first)).toBe(true)

      // After the grace period it is reclaimed; the displayed one stays.
      await act(async () => {
        vi.advanceTimersByTime(31_000)
      })
      expect(live.has(first)).toBe(false)
      expect(live.has(second)).toBe(true)
    } finally {
      vi.useRealTimers()
    }
  })
})
