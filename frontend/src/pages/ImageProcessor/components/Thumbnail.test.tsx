import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import Thumbnail from './Thumbnail'

// Мокаем imageApi чтобы избежать реальных HTTP-вызовов
vi.mock('../imageApi', () => ({
  imageApi: {
    getPreview: vi.fn(),
    getResultPreview: vi.fn(),
  },
}))

import { imageApi } from '../imageApi'

describe('Thumbnail', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('показывает fallback-иконку до загрузки preview', async () => {
    vi.mocked(imageApi.getPreview).mockResolvedValue('blob:mock-1')
    render(
      <Thumbnail
        taskId="task-1"
        status="pending"
        fileExists={false}
        operation="remove_bg"
      />,
    )
    expect(screen.getByTestId('thumbnail-fallback')).toBeInTheDocument()
  })

  it('использует getResultPreview при status=ready', async () => {
    vi.mocked(imageApi.getResultPreview).mockResolvedValue('blob:mock-result')
    render(
      <Thumbnail
        taskId="task-ready"
        status="ready"
        fileExists={true}
        operation="remove_bg"
      />,
    )
    await waitFor(() => {
      expect(imageApi.getResultPreview).toHaveBeenCalledWith('task-ready')
    })
  })

  it('использует getPreview при status=processing', async () => {
    vi.mocked(imageApi.getPreview).mockResolvedValue('blob:mock-input')
    render(
      <Thumbnail
        taskId="task-proc"
        status="processing"
        fileExists={false}
        operation="remove_watermark"
      />,
    )
    await waitFor(() => {
      expect(imageApi.getPreview).toHaveBeenCalledWith('task-proc')
    })
  })

  it('освобождает blob URL при unmount', async () => {
    vi.mocked(imageApi.getResultPreview).mockResolvedValue('blob:mock-cleanup')
    const revokeSpy = vi.spyOn(URL, 'revokeObjectURL')
    const { unmount } = render(
      <Thumbnail
        taskId="task-cleanup"
        status="ready"
        fileExists={true}
        operation="remove_bg"
      />,
    )
    await waitFor(() => {
      expect(imageApi.getResultPreview).toHaveBeenCalled()
    })
    unmount()
    expect(revokeSpy).toHaveBeenCalledWith('blob:mock-cleanup')
  })

  it('показывает fallback при ошибке загрузки', async () => {
    vi.mocked(imageApi.getResultPreview).mockRejectedValue(new Error('404'))
    render(
      <Thumbnail
        taskId="task-gone"
        status="ready"
        fileExists={false}
        operation="remove_bg"
      />,
    )
    await waitFor(() => {
      expect(screen.getByTestId('thumbnail-fallback')).toBeInTheDocument()
    })
  })

  it('освобождает старый URL при смене taskId', async () => {
    vi.mocked(imageApi.getResultPreview)
      .mockResolvedValueOnce('blob:A')
      .mockResolvedValueOnce('blob:B')
    const revokeSpy = vi.spyOn(URL, 'revokeObjectURL')

    const { rerender } = render(
      <Thumbnail taskId="task-A" status="ready" fileExists={true} operation="remove_bg" />,
    )
    await waitFor(() => {
      expect(imageApi.getResultPreview).toHaveBeenCalledWith('task-A')
    })
    // Дать React применить setUrl('blob:A') — после waitFor блоб уже во стейте.

    rerender(
      <Thumbnail taskId="task-B" status="ready" fileExists={true} operation="remove_bg" />,
    )
    await waitFor(() => {
      expect(imageApi.getResultPreview).toHaveBeenCalledWith('task-B')
    })
    await waitFor(() => {
      expect(revokeSpy).toHaveBeenCalledWith('blob:A')
    })
  })

  it('освобождает блоб, если loader резолвится после unmount', async () => {
    let resolveLoader: (value: string) => void = () => {}
    const deferred = new Promise<string>((res) => {
      resolveLoader = res
    })
    vi.mocked(imageApi.getResultPreview).mockReturnValue(deferred)
    const revokeSpy = vi.spyOn(URL, 'revokeObjectURL')

    const { unmount } = render(
      <Thumbnail taskId="task-late" status="ready" fileExists={true} operation="remove_bg" />,
    )
    // Ждём, пока loader будет вызван (после IO-мока и effect 2).
    await waitFor(() => {
      expect(imageApi.getResultPreview).toHaveBeenCalledWith('task-late')
    })
    unmount()
    resolveLoader('blob:late')
    // Даём микрозадаче разрешиться:
    await Promise.resolve()
    await Promise.resolve()
    expect(revokeSpy).toHaveBeenCalledWith('blob:late')
  })
})
