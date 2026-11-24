# Playwright Test (Node/TypeScript) patterns

For projects that already use `@playwright/test`. Run through
`qast exec playwright --group <g> -- <args>`: the adapter adds `--reporter=json` and
`--output=<run work dir>/test-results`, so screenshots and traces declared as
attachments are hashed and linked to their test automatically.

## Configuration

Use the project's `playwright.config.ts`. If new specs must live in
`permissions.test_dir` and the project's `testDir` does not include it, add a QA config
*inside* `test_dir` instead of editing the project's config:

```ts
// tests/qa/playwright.qa.config.ts
import { defineConfig } from '@playwright/test';
import base from '../../playwright.config';

export default defineConfig({
  ...base,
  testDir: '.',                   // relative to this file
  retries: 0,                     // evidence runs: flakiness goes through qast reproduce
  use: {
    ...base.use,
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  // webServer.cwd defaults to the config file's directory: point it at the project root.
  webServer: base.webServer && !Array.isArray(base.webServer)
    ? { ...base.webServer, cwd: '../..', reuseExistingServer: false }
    : base.webServer,
});
```

`qast exec playwright --group critical-journeys -- --config tests/qa/playwright.qa.config.ts`

Without a `webServer` entry, start the app yourself on a local port and pass
`baseURL` through the config; never point `baseURL` at a host outside
`permissions.authorized_targets`.

## Journey with validation-error recovery

```ts
// tests/qa/booking-recovery.qa.spec.ts
import { expect, test, type Page } from '@playwright/test';

async function reachAddressStep(page: Page) {
  await page.getByLabel('Full name').fill('Noor Haddad');
  await page.getByLabel('Email').fill('noor@example.com');
  await page.getByRole('button', { name: 'Continue' }).click();
  await expect(page.getByRole('heading', { name: 'Address' })).toBeVisible();
}

test('recovers from an invalid email and completes in the same session', async ({ page }) => {
  await page.goto('/');
  await page.getByLabel('Full name').fill('Noor Haddad');
  const email = page.getByLabel('Email');
  await email.fill('noor.example.com');
  await page.getByRole('button', { name: 'Continue' }).click();
  await expect(email).toHaveAttribute('aria-invalid', 'true');
  await expect(page.getByRole('heading', { name: 'Your details' })).toBeVisible();

  await email.fill('noor@example.com');
  await page.getByRole('button', { name: 'Continue' }).click();
  await expect(email).not.toHaveAttribute('aria-invalid', 'true');
  await expect(page.getByRole('heading', { name: 'Address' })).toBeVisible();

  await page.getByLabel('Postal code').fill('10115');
  await page.getByRole('button', { name: 'Continue' }).click();
  await page.getByRole('button', { name: 'Confirm booking' }).click();
  await expect(page.getByText(/BK-\d+/)).toBeVisible();
});

test('server error keeps the user on review and retry succeeds', async ({ page }) => {
  const bodies: unknown[] = [];
  await page.route('**/api/bookings', async (route) => {
    bodies.push(route.request().postDataJSON());
    if (bodies.length === 1) {
      await route.fulfill({ status: 503, contentType: 'application/json', body: '{"error":"unavailable"}' });
    } else {
      await route.continue();
    }
  });
  await page.goto('/');
  await reachAddressStep(page);
  await page.getByLabel('Postal code').fill('10115');
  await page.getByRole('button', { name: 'Continue' }).click();
  await page.getByRole('button', { name: 'Confirm booking' }).click();
  await expect(page.getByRole('button', { name: 'Retry' })).toBeVisible();
  await page.getByRole('button', { name: 'Retry' }).click();
  await expect(page.getByText(/BK-\d+/)).toBeVisible();
  expect(bodies).toHaveLength(2);
  expect(bodies[1]).toEqual(bodies[0]);
});
```

## Viewports, locales and RTL as projects

```ts
// inside defineConfig({ projects: [...] }) of the QA config
import { devices } from '@playwright/test';

projects: [
  { name: 'desktop', use: { ...devices['Desktop Chrome'] } },
  { name: 'mobile-375', use: { ...devices['Desktop Chrome'], viewport: { width: 375, height: 812 }, hasTouch: true } },
  { name: 'rtl-ar', use: { ...devices['Desktop Chrome'], locale: 'ar-SA' } },
],
```

A per-describe override is lighter when only some specs need it:

```ts
test.describe('375px', () => {
  test.use({ viewport: { width: 375, height: 812 } });

  test('no horizontal scroll on any step', async ({ page }) => {
    await page.goto('/?lang=ar');
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(0);
  });
});
```

Result identifiers include the project name (`file::title [mobile-375]`); pass them to
`qast reproduce` exactly as printed.

## Network control

- `route.abort('internetdisconnected' | 'failed' | 'timedout')`, `route.fulfill({ status })`.
- Hold a request to observe loading states and double submits: store the `route` in an
  array inside the handler, act, then `await route.continue()`.
- `const response = page.waitForResponse('**/api/bookings'); await click; expect((await response).status()).toBe(201);`
- `page.on('pageerror', e => errors.push(e.message))` and assert `errors` is empty for
  journeys without injected failures.

## Visual regression: only against valid, existing baselines

```bash
qast exec playwright --group critical-journeys -- --update-snapshots=none tests/visual
```

- Run visual comparisons only when the repository already contains reviewed baselines
  (`*-snapshots/` next to the spec) for the **same browser and OS** they were generated
  on; the platform is part of the file name (`booking-review-chromium-linux.png`).
- Always pass `--update-snapshots=none`. The default (`missing`) silently writes a new
  baseline for every missing snapshot, which is creating a baseline.
- Never run `--update-snapshots` / `-u` to make a comparison pass, never edit, delete or
  regenerate a baseline file, and never raise `maxDiffPixels`/`threshold` to absorb a diff.
- A missing baseline is NOT_RUN ("no baseline"), not a pass and not a product defect.
- A diff is INCONCLUSIVE until a human reviews it, unless the diff image shows an
  unambiguous defect (clipped text, overlapping controls, missing element). Cite the
  diff artifact id in the finding.

## Accessibility hand-off

Journey specs can collect app states for `qa-accessibility` (URL + the steps to reach
it). The axe injection snippet (TS and Python) lives in that skill's
`references/playwright-axe-injection.md`; reuse it rather than writing a second one.
