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
})
