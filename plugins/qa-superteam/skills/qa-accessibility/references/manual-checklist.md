# Manual validation checklist

Everything here is **not automated**. Unless a human (or a scripted check you actually
executed and recorded) performed an item, the report lists it under "not verified"
with the reason. Never mark these as passed because the automated scan was clean.

Record the open items once per run:

```bash
qast run note --kind limitation "Accessibility manual validation not performed: screen reader (NVDA/VoiceOver), 200% zoom, reflow visual check, motion, non-text contrast of focus indicators. Automated axe scans cover WCAG A/AA rules on the listed states only."
```

When the user (or a reviewer) performs an item and reports the outcome, record what they
observed in a finding (if it failed) or as a `decision` note with who checked what, on
which browser/AT, and when.

## Screen reader (NVDA + Firefox/Chrome on Windows, VoiceOver + Safari on macOS/iOS, TalkBack on Android)

- [ ] Page title and main heading announced on load and on every step change (SPA).
- [ ] Every form control announces name, role, state, required/invalid and its
      description (error or hint).
- [ ] Validation errors are announced when they appear (live region / `role="alert"`),
      once, and in the active language.
- [ ] Async status (loading, saved, order placed, retry available) announced (4.1.3).
- [ ] Reading order matches visual order, including in RTL views (1.3.2).
- [ ] Custom widgets (comboboxes, date pickers, dialogs, tabs) follow their ARIA
      authoring pattern; dialogs trap focus while open and return it on close.
- [ ] Images: alt text conveys the same information; decorative images silent.
- [ ] Links and buttons distinguishable out of context ("Remove", not "Click here"
      repeated).

## Zoom, reflow and text

- [ ] Browser zoom 200 %: no loss of content or function, no overlapping text (1.4.4).
- [ ] 400 % zoom / 320 CSS px width: single-column reflow, no two-dimensional scrolling
      except for data tables, maps, diagrams (1.4.10). Automated overflow check is an
      approximation; confirm visually.
- [ ] Text spacing override (line height 1.5, paragraph spacing 2×, letter 0.12em,
      word 0.16em): nothing clipped or overlapping (1.4.12).
- [ ] OS/browser large text and high-contrast/forced-colors mode
      (`forced-colors: active`): controls and focus still visible.

## Keyboard and focus (beyond the scripted checks)

- [ ] Focus indicator visible on every interactive element, ≥ 3:1 against adjacent
      colours, not hidden behind sticky headers or cookie banners (2.4.7, 2.4.11, 1.4.11).
- [ ] No keyboard trap anywhere, including embedded third-party widgets (payment
      iframes, chat) (2.1.2).
- [ ] Shortcuts using single characters can be turned off or remapped (2.1.4).
- [ ] Focus moves predictably after actions (step change, dialog close, item removal).

## Motion, timing and media

- [ ] `prefers-reduced-motion: reduce` honoured; no parallax or auto-animating content
      without a pause control (2.2.2, 2.3.3 AAA advisory).
- [ ] Nothing flashes more than three times per second (2.3.1).
- [ ] Session or step timeouts warn and can be extended (2.2.1).
- [ ] Video has accurate captions; audio has transcripts; autoplaying media can be
      paused (1.2.x, 1.4.2).

## Language, direction and content

- [ ] `lang` correct for the page and for passages in another language (3.1.1, 3.1.2).
- [ ] RTL views: reading order, alignment, mirrored icons and form flows make sense to a
      native reader; mixed-direction strings (emails, numbers, product codes) render
      correctly.
- [ ] Error messages explain how to fix the problem (3.3.3); purchases/bookings can be
      reviewed and corrected before submission (3.3.4).
- [ ] Instructions do not rely on shape, colour, size or position alone (1.3.3, 1.4.1).
- [ ] Help mechanisms appear in the same place across pages (3.2.6); users are not
      asked to re-enter information already given in the same process (3.3.7).
- [ ] Authentication does not require a cognitive test without an alternative; password
      managers and paste work (3.3.8).

## Pointer and touch

- [ ] Targets at least 24×24 CSS px or with sufficient spacing (2.5.8); check at 375 px.
- [ ] Every drag operation has a single-pointer alternative (2.5.7).
- [ ] Actions fire on up-event or can be aborted (2.5.2).
- [ ] Visible label text is contained in the accessible name (2.5.3).

## How to phrase the result

"Automated: axe-core <version> (WCAG 2.0/2.1 A/AA[, 2.2 AA]) on N states (list) found
X violations (Y serious/critical) and Z items needing manual review. Scripted keyboard,
focus and reflow checks: <statuses>. Manual validation (screen reader, zoom, motion,
contrast of non-text elements): not performed." Never "the site is accessible" or
"WCAG compliant".
