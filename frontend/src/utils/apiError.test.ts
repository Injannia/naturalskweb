import { describe, it, expect } from 'vitest'
import { AxiosError, AxiosHeaders } from 'axios'
import { extractApiError } from './apiError'

function axiosErrWith(data: unknown): AxiosError {
  const err = new AxiosError('boom')
  err.response = {
    data,
    status: 422,
    statusText: '',
    headers: {},
    config: { headers: new AxiosHeaders() },
  }
  return err
}

describe('extractApiError', () => {
  it('returns a string detail as-is', () => {
    expect(extractApiError(axiosErrWith({ detail: 'Файл слишком большой' }))).toBe('Файл слишком большой')
  })

  it('unwraps the first msg of a 422 validation array', () => {
    const err = axiosErrWith({ detail: [{ loc: ['body', 'url'], msg: 'Введите корректную ссылку', type: 'value_error' }] })
    expect(extractApiError(err)).toBe('Введите корректную ссылку')
  })

  it('strips the pydantic "Value error," prefix', () => {
    const err = axiosErrWith({ detail: [{ msg: 'Value error, Ссылка не должна быть пустой', type: 'value_error' }] })
    expect(extractApiError(err)).toBe('Ссылка не должна быть пустой')
  })

  it('falls back when detail is missing', () => {
    expect(extractApiError(axiosErrWith({}), 'Не удалось')).toBe('Не удалось')
  })

  it('falls back for non-axios errors', () => {
    expect(extractApiError(new Error('nope'), 'Резерв')).toBe('Резерв')
  })

  it('uses the default fallback when none provided', () => {
    expect(extractApiError(new Error('x'))).toBe('Произошла ошибка')
  })
})
