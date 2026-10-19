import { defineConfig } from 'vitest/config';
export default defineConfig({
  cacheDir: './.vite-cache',
  test: { environment: 'jsdom', globals: true, setupFiles: ['./setup.ts'], include: ['src/**/*.test.{ts,tsx}'], css: { modules: { classNameStrategy: 'non-scoped' } } },
});
