import axios from 'axios'

/**
 * Pull a human-readable message out of an error returned by the API.
 *
 * FastAPI's `detail` is a plain string for handled 4xx/5xx errors, but an
 * array of `{ loc, msg, type }` objects for 422 request-validation errors.
 * Blindly stringifying that array yields the infamous "[object Object]" toast,
 * so this helper handles both shapes and strips pydantic's "Value error, "
 * prefix from validator messages.
 */
export function extractApiError(err: unknown, fallback = 'Произошла ошибка'): string {
  if (axios.isAxiosError(err)) {
    const detail = err.response?.data?.detail
    if (typeof detail === 'string' && detail.trim()) return detail
    if (Array.isArray(detail) && typeof detail[0]?.msg === 'string') {
      return detail[0].msg.replace(/^Value error,\s*/i, '')
    }
  }
  return fallback
}
