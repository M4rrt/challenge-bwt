import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

// jsdom doesn't implement scroll geometry/behavior.
Element.prototype.scrollIntoView = () => {}

// jsdom's matchMedia always reports matches: false, which makes MUI's
// useMediaQuery-based breakpoints default to the mobile branch in every
// test. Default to "matches" so existing tests keep seeing desktop layout
// unless a test explicitly overrides window.matchMedia for a mobile case.
window.matchMedia = ((query: string) => ({
  matches: true,
  media: query,
  onchange: null,
  addListener: () => {},
  removeListener: () => {},
  addEventListener: () => {},
  removeEventListener: () => {},
  dispatchEvent: () => false,
})) as typeof window.matchMedia

afterEach(() => {
  cleanup()
})
