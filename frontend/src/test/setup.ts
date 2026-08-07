import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

// jsdom doesn't implement scroll geometry/behavior.
Element.prototype.scrollIntoView = () => {}

afterEach(() => {
  cleanup()
})
