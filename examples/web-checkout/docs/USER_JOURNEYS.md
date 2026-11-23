# Critical user journeys

These are the journeys the checkout must support before a release. Each lists the acceptance criteria the
product team signs off on. Money values assume the default cart: Everyday Canvas Tote $48.00 + Ceramic
Pour-Over Set $32.00 = **$80.00 subtotal**.

## J1. Checkout end to end

A shopper enters valid details and places an order.

- Contact requires a full name and a valid email address.
- Shipping requires a country and a postal code valid for that country (US and SA: 5 digits; CA: `A1A 1A1`).
- Shipping cost follows the country: US $5.00, CA $12.00, SA $20.00, and the order summary updates as soon as
  the country changes.
- Review shows the entered contact and shipping details, every cart item with its price, the subtotal,
  shipping, any discount, and the total (`subtotal + shipping - discount`).
- **Place order** shows a confirmation with an order number of the form `ORD-<n>`.

## J2. Recover from a validation error

A shopper makes a typo, sees the problem, fixes it and carries on, without losing data or reloading.

- Invalid or missing input shows an inline message next to the field; the message is announced to assistive
  technology (`role="alert"`) and linked to the field (`aria-describedby`, `aria-invalid`).
- Submitting a step with an error keeps the shopper on that step.
- As soon as the value is corrected the message disappears, and the shopper can continue to the next step
  and complete the order (J1) **in the same page session**.
- This applies to every step: name and email on Contact, postal code (including after a country change) on
  Shipping.

## J3. Apply and remove a promo code

- On Review, entering `SAVE10` (any letter case) and choosing **Apply** takes 10% off the subtotal ($8.00), shows
  a discount line and a "SAVE10 applied" badge, and updates the total ($85.00 to $77.00 for US shipping).
- An unknown code shows "That promo code isn't valid." and leaves the totals unchanged.
- **Remove** clears the code and the badge, hides the discount line, and restores every total to its value
  without a discount ($85.00 for US shipping). The amount charged must always match the totals shown.

## J4. Resume and go back

- **Back** from Shipping or Review returns to the previous step with every field still filled in.
- Reloading the page (or returning later in the same browser) on Shipping or Review resumes on that step with
  the entered data restored. The page never resumes past a step whose data is incomplete.
- After a successful order the draft is discarded; reloading starts a new checkout.

## J5. Order placement fails

- If the order request fails (network error or a non-201 response), the shopper stays on Review and sees
  "We couldn't place your order. Please try again." with a **Retry** button. Entered data is kept.
- **Retry** submits the order again; on success the banner disappears and the confirmation is shown.

## J6. Arabic / right-to-left

- `?lang=ar` renders all labels, buttons, messages and the order summary in Arabic and sets
  `<html lang="ar" dir="rtl">`. The layout mirrors (labels and actions align to the right).
- J1 to J5 work identically in Arabic.

## J7. Mobile

- At a 375px-wide viewport every step, error state and the confirmation fit without horizontal scrolling,
  in both English and Arabic. Long names and emails wrap instead of overflowing.
- All actions remain reachable and tappable.

## Accessibility (applies to all journeys)

- Target: WCAG 2.1 AA. Automated checks (axe-core) must report no serious or critical violations on any step.
- Every form control has an accessible name.
- Everything is operable by keyboard; focus moves to the step heading when the step changes, and interactive
  controls show a visible focus indicator.
- Text and controls meet AA colour-contrast requirements.
