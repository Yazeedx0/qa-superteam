# WCAG 2.2 AA and axe-core: what the rules cover, and what they do not

axe-core finds a subset of WCAG failures reliably (roughly a third of the success
criteria can be partly checked by rules). "No violations" means "none of the automated
rules failed on the states scanned", never "conforms to WCAG". Rule ids and tags below
are axe-core 4.x; check `axe_version` in the result file and the rule's `helpUrl` when in
doubt.

## Which rules run

- `qast exec axe` runs the tags `wcag2a, wcag2aa, wcag21a, wcag21aa`. WCAG 2.2-only rules
  (tag `wcag22aa`, e.g. `target-size`) and `best-practice` rules do **not** run there.
  Use the in-test injection with `wcag22aa` added when the target is WCAG 2.2.
- `experimental` rules (e.g. `label-content-name-mismatch`) never run unless enabled.
- 4.1.1 Parsing is obsolete in WCAG 2.2; recent axe versions retired the generic
  duplicate-id rules and tag `duplicate-id-aria` as 4.1.2. A duplicated id matters when it
  breaks a label or `aria-describedby` reference.
- Mapping verified against axe-core 4.14 (`axe.getRules()`); older versions differ in
  places, so trust the `tags` in your result file over this table.

## Common rules mapped to success criteria

| axe rule | WCAG 2.2 SC | Level | Notes |
|---|---|---|---|
| `image-alt`, `input-image-alt`, `role-img-alt`, `svg-img-alt`, `object-alt` | 1.1.1 Non-text Content | A | Decorative images need `alt=""`, not a missing alt; alt *quality* is manual |
| `video-caption` | 1.2.2 Captions (Prerecorded) | A | Caption accuracy is manual |
| `list`, `listitem`, `definition-list`, `dlitem`, `td-headers-attr`, `th-has-data-cells`, `aria-required-children`, `aria-required-parent` | 1.3.1 Info and Relationships | A | |
| `autocomplete-valid` | 1.3.5 Identify Input Purpose | AA | Only checks validity of the token, not that personal-data fields have one |
| `link-in-text-block` | 1.4.1 Use of Color | A | |
| `no-autoplay-audio` | 1.4.2 Audio Control | A | |
| `color-contrast` | 1.4.3 Contrast (Minimum) | AA | Text over images/gradients ends up in `incomplete` → manual |
| `meta-viewport` | 1.4.4 Resize Text | AA | Flags `user-scalable=no` / `maximum-scale` < 2 |
| `avoid-inline-spacing` | 1.4.12 Text Spacing | AA | Only inline `!important` styles; real spacing test is manual/approximation |
| `scrollable-region-focusable`, `server-side-image-map` | 2.1.1 Keyboard (and 2.1.3) | A | Most keyboard operability is not rule-checkable |
| `meta-refresh` | 2.2.1 Timing Adjustable | A | |
| `blink`, `marquee` | 2.2.2 Pause, Stop, Hide | A | |
| `bypass` | 2.4.1 Bypass Blocks | A | |
| `document-title` | 2.4.2 Page Titled | A | Title *meaningfulness* is manual |
| `link-name`, `area-alt` | 2.4.4 Link Purpose (In Context), 4.1.2 | A | |
| `target-size` | 2.5.8 Target Size (Minimum) | AA (2.2) | Tag `wcag22aa`: only via injection with that tag |
| `label-content-name-mismatch` | 2.5.3 Label in Name | A | Experimental: enable explicitly |
| `html-has-lang`, `html-lang-valid`, `html-xml-lang-mismatch` | 3.1.1 Language of Page | A | For RTL views also check `dir="rtl"` (not a WCAG rule; requirement-driven) |
| `valid-lang` | 3.1.2 Language of Parts | AA | Only validates codes that exist; missing `lang` on foreign passages is manual |
| `label`, `select-name`, `input-button-name`, `button-name`, `frame-title`, `aria-input-field-name`, `aria-toggle-field-name`, `nested-interactive` | 4.1.2 Name, Role, Value | A | Visible label presence (3.3.2) is manual: axe accepts `placeholder`, `title` and `aria-label` as names |
| `aria-allowed-attr`, `aria-required-attr`, `aria-valid-attr`, `aria-valid-attr-value`, `aria-roles`, `aria-hidden-focus`, `aria-hidden-body` | 4.1.2 Name, Role, Value | A | |

Best-practice rules (`region`, `landmark-*`, `heading-order`, `page-has-heading-one`,
`empty-heading`) are not WCAG failures by themselves; report them as `info`/`low`
observations unless they cause a real SC failure (e.g. 1.3.1 when headings are faked
with styled `div`s).

## Success criteria that need scripted or manual checks

| SC | Level | How to check |
|---|---|---|
| 1.3.2 Meaningful Sequence | A | Compare DOM/reading order with visual order (tab order test, screen reader) |
| 1.3.4 Orientation | AA | Rotate viewport (e.g. 812×375); content must not be locked (axe `css-orientation-lock` is experimental) |
| 1.4.10 Reflow | AA | Scripted approximation: 320 CSS px wide, no horizontal scroll; confirm visually |
| 1.4.11 Non-text Contrast | AA | Input borders, focus rings, icons ≥ 3:1: manual (screenshot + contrast tool) |
| 1.4.12 Text Spacing | AA | Scripted approximation (inject spacing CSS, look for clipped text); confirm visually |
| 1.4.13 Content on Hover or Focus | AA | Tooltips dismissible (Esc), hoverable, persistent: scripted per widget |
| 2.1.2 No Keyboard Trap | A | Scripted: Tab/Shift+Tab leave every widget; Esc closes modals |
| 2.4.3 Focus Order | A | Scripted tab sequence vs logical order |
| 2.4.6 Headings and Labels | AA | Manual: descriptive text |
| 2.4.7 Focus Visible | AA | Scripted approximation (style changes on keyboard focus); visibility manual |
| 2.4.11 Focus Not Obscured (Minimum) | AA (2.2) | Manual/scripted: focused element not fully hidden by sticky headers/banners |
| 2.5.7 Dragging Movements | AA (2.2) | Manual: single-pointer alternative for every drag |
| 3.2.1 / 3.2.2 On Focus / On Input | A | Scripted: focusing/changing a field does not navigate or submit |
| 3.2.6 Consistent Help | A (2.2) | Manual across pages |
| 3.3.1 Error Identification | A | Scripted: error text exists, is associated (`aria-describedby`), field marked `aria-invalid` |
| 3.3.2 Labels or Instructions | A | Visible label for every input (placeholder alone fails) |
| 3.3.3 Error Suggestion | AA | Manual: the message says how to fix it |
| 3.3.4 Error Prevention (Legal, Financial, Data) | AA | For purchases/bookings/payments: review step, confirmation or reversal exists |
| 3.3.7 Redundant Entry | A (2.2) | Previously entered data is not requested again in the same process |
| 3.3.8 Accessible Authentication (Minimum) | AA (2.2) | No cognitive test without alternative; paste allowed in password fields |
| 4.1.3 Status Messages | AA | Scripted: async messages use `role="status"`/`"alert"` or `aria-live`; screen reader confirmation manual |

## From axe result to a finding

| axe outcome | qast status | Report as |
|---|---|---|
| `violations` (rule failed on ≥1 node) | FAILED | Finding (category `accessibility`) after confirming the node is real and visible to users |
| `incomplete` (rule could not decide) | INCONCLUSIVE | "Needs manual review" item; never a pass, never a defect claim |
| `passes` | PASSED (per rule, per page state) | Only "rule X found no violations on state Y" |
| Scan could not run (no axe-core, no browser, unauthorized target) | BLOCKED | Limitation with the unblock step |

Severity is about user impact on the journey, not axe's `impact` field alone:

| Severity | When |
|---|---|
| critical | A disability group cannot complete an essential journey (unlabelled payment/submit control, keyboard trap, focus lost in a modal with no escape, error never announced on a required step) |
| high | Essential journey possible only with significant effort (contrast failures on primary actions, errors not associated with fields, missing names on key controls with visible text nearby) |
| medium | Failure on a secondary page/state, or partial impact on an essential one |
| low | Minor, rare or cosmetic impact (redundant alt text, heading level skip) |
| info | Best-practice observations without an SC failure |

One finding per rule *and* root cause (group all nodes of `label` on the same widget);
list node selectors, page state (URL + steps), viewport, locale, and the result JSON
evidence id.
