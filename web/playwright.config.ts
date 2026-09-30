import { defineConfig, devices } from '@playwright/test';
import os from 'node:os';
import path from 'node:path';
import fs from 'node:fs';

const PORT = Number(process.env.E2E_PORT || 8123);
const dataDir = path.join(os.tmpdir(), `qveris-e2e-${Date.now()}`);
const chromium = process.env.PW_CHROMIUM || (fs.existsSync('/opt/pw-browsers/chromium-1194/chrome-linux/chrome') ? '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' : undefined);

export default defineConfig({
  testDir: './e2e',
  timeout: 90_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list']],
  outputDir: 'e2e/artifacts/results',
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    launchOptions: { executablePath: chromium, args: ['--use-gl=swiftshader', '--enable-webgl', '--ignore-gpu-blocklist'] },
    screenshot: 'only-on-failure',
  },
  projects: [
    { name: 'desktop', use: { viewport: { width: 1440, height: 900 } } },
    { name: 'mobile', use: { ...devices['Pixel 7'], browserName: 'chromium', viewport: { width: 390, height: 844 } }, testMatch: /smoke|mobile/ },
  ],
  webServer: {
    command: `python -m server --port ${PORT}`,
    cwd: '..',
    url: `http://127.0.0.1:${PORT}/api/v1/health`,
    timeout: 120_000,
    reuseExistingServer: false,
    env: { PYTHONPATH: 'src', QVERIS_DATA_DIR: dataDir, QVERIS_PRESET: 'demo', QVERIS_AUTOSTART_TRAFFIC: '0', QVERIS_HEAVY_BURST: '1000', QVERIS_HEAVY_REFILL: '100', QVERIS_LOG_LEVEL: 'WARNING' },
  },
});
