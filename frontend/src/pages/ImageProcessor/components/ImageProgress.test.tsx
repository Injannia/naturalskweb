import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import ImageProgress from './ImageProgress'
import type { ImageTaskListItem } from '../types'

// Замокаем Thumbnail — не хотим сетевых вызовов в тестах ImageProgress
vi.mock('./Thumbnail', () => ({
  default: () => <div data-testid="thumbnail" />,
}))

function makeTask(overrides: Partial<ImageTaskListItem> = {}): ImageTaskListItem {
  return {
    task_id: 'task-1',
    status: 'ready',
    progress: 100,
    operation: 'remove_bg',
    filename: 'result.png',
    file_size: 1024,
    error: null,
    original_filename: 'input.jpg',
    original_ext: 'jpg',
    inpaint_method: null,
    created_at: '2026-04-21T10:00:00',
    completed_at: '2026-04-21T10:00:05',
    file_exists: true,
    ...overrides,
  }
}

describe('ImageProgress', () => {
  it('показывает имя файла и thumbnail', () => {
    render(
      <ImageProgress
        task={makeTask()}
        onDismiss={vi.fn()}
        onRestore={vi.fn()}
        onDownload={vi.fn()}
        onDelete={vi.fn()}
      />,
    )
    expect(screen.getByText('input.jpg')).toBeInTheDocument()
    expect(screen.getByTestId('thumbnail')).toBeInTheDocument()
  })

  it('при ready + !isHistory показывает Скачать / Скрыть / Удалить', () => {
    render(
      <ImageProgress
        task={makeTask({ status: 'ready' })}
        onDismiss={vi.fn()}
        onRestore={vi.fn()}
        onDownload={vi.fn()}
        onDelete={vi.fn()}
      />,
    )
    expect(screen.getByRole('button', { name: /скачать/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /скрыть/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /удалить/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /восстановить/i })).not.toBeInTheDocument()
  })

  it('при ready + isHistory показывает Скачать / Восстановить / Удалить', () => {
    render(
      <ImageProgress
        task={makeTask({ status: 'ready' })}
        isHistory
        onDismiss={vi.fn()}
        onRestore={vi.fn()}
        onDownload={vi.fn()}
        onDelete={vi.fn()}
      />,
    )
    expect(screen.getByRole('button', { name: /скачать/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /восстановить/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /удалить/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /скрыть/i })).not.toBeInTheDocument()
  })

  it('при processing не показывает никаких кнопок действий', () => {
    render(
      <ImageProgress
        task={makeTask({ status: 'processing', progress: 42 })}
        onDismiss={vi.fn()}
        onRestore={vi.fn()}
        onDownload={vi.fn()}
        onDelete={vi.fn()}
      />,
    )
    expect(screen.queryByRole('button', { name: /скачать/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /скрыть/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /удалить/i })).not.toBeInTheDocument()
  })

  it('показывает прогресс-бар при processing', () => {
    render(
      <ImageProgress
        task={makeTask({ status: 'processing', progress: 42 })}
        onDismiss={vi.fn()}
        onRestore={vi.fn()}
        onDownload={vi.fn()}
        onDelete={vi.fn()}
      />,
    )
    expect(screen.getByRole('progressbar')).toBeInTheDocument()
  })

  it('при error + !isHistory показывает Скрыть / Удалить, но не Скачать', () => {
    render(
      <ImageProgress
        task={makeTask({ status: 'error', error: 'boom' })}
        onDismiss={vi.fn()}
        onRestore={vi.fn()}
        onDownload={vi.fn()}
        onDelete={vi.fn()}
      />,
    )
    expect(screen.queryByRole('button', { name: /скачать/i })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /скрыть/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /удалить/i })).toBeInTheDocument()
  })

  it('Скачать отсутствует если file_exists=false', () => {
    render(
      <ImageProgress
        task={makeTask({ status: 'ready', file_exists: false })}
        onDismiss={vi.fn()}
        onRestore={vi.fn()}
        onDownload={vi.fn()}
        onDelete={vi.fn()}
      />,
    )
    expect(screen.queryByRole('button', { name: /скачать/i })).not.toBeInTheDocument()
  })

  it('onDownload получает task_id', () => {
    const onDownload = vi.fn()
    render(
      <ImageProgress
        task={makeTask({ task_id: 'abc' })}
        onDismiss={vi.fn()}
        onRestore={vi.fn()}
        onDownload={onDownload}
        onDelete={vi.fn()}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: /скачать/i }))
    expect(onDownload).toHaveBeenCalledWith('abc')
  })

  it('onDismiss получает task_id', () => {
    const onDismiss = vi.fn()
    render(
      <ImageProgress
        task={makeTask({ task_id: 'def' })}
        onDismiss={onDismiss}
        onRestore={vi.fn()}
        onDownload={vi.fn()}
        onDelete={vi.fn()}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: /скрыть/i }))
    expect(onDismiss).toHaveBeenCalledWith('def')
  })

  it('onRestore вызывается в режиме isHistory', () => {
    const onRestore = vi.fn()
    render(
      <ImageProgress
        task={makeTask({ task_id: 'hist-1' })}
        isHistory
        onDismiss={vi.fn()}
        onRestore={onRestore}
        onDownload={vi.fn()}
        onDelete={vi.fn()}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: /восстановить/i }))
    expect(onRestore).toHaveBeenCalledWith('hist-1')
  })
})
