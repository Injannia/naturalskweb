import '@testing-library/jest-dom'

// jsdom не реализует IntersectionObserver, а Thumbnail его использует.
class MockIntersectionObserver implements IntersectionObserver {
  readonly root = null
  readonly rootMargin = ''
  readonly thresholds = []
  constructor(private callback: IntersectionObserverCallback) {}
  observe(target: Element): void {
    // Имитируем мгновенное попадание в viewport — упрощает тесты,
    // которые проверяют реакцию на visibility.
    this.callback(
      [
        {
          isIntersecting: true,
          target,
          intersectionRatio: 1,
          time: 0,
          boundingClientRect: {} as DOMRectReadOnly,
          intersectionRect: {} as DOMRectReadOnly,
          rootBounds: null,
        },
      ],
      this,
    )
  }
  unobserve(): void {}
  disconnect(): void {}
  takeRecords(): IntersectionObserverEntry[] { return [] }
}

;(globalThis as unknown as { IntersectionObserver: unknown }).IntersectionObserver = MockIntersectionObserver

// URL.createObjectURL / revokeObjectURL в jsdom — стаб с предсказуемыми значениями
if (typeof URL.createObjectURL !== 'function') {
  let counter = 0
  URL.createObjectURL = () => `blob:mock-${counter++}`
  URL.revokeObjectURL = () => {}
}
