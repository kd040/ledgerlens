import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
// vitest/config re-exports Vite's defineConfig with the `test` block
// typed, so the app config and the test config stay in one file.
import { defineConfig } from 'vitest/config'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  // Tests import describe/it/expect from 'vitest' explicitly, so no
  // globals are injected; jsdom + the jest-dom matchers are the only
  // things the component tests actually need.
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
  },
})
