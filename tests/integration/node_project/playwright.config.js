// CHROMIUM_EXECUTABLE lets CI/dev machines reuse an already-installed Chromium build.
export default {
  testDir: 'e2e',
  use: { launchOptions: { executablePath: process.env.CHROMIUM_EXECUTABLE || undefined } },
};
