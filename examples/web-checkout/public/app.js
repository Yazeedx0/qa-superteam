(() => {
  'use strict';

  const STORAGE_KEY = 'checkout.draft.v1';
  const STEPS = ['contact', 'shipping', 'review'];
  const CART = [
    { sku: 'TOTE-01', nameKey: 'itemTote', qty: 1, price: 4800 },
    { sku: 'POUR-02', nameKey: 'itemPourOver', qty: 1, price: 3200 },
  ];
  const SHIPPING_RATES = { US: 500, CA: 1200, SA: 2000 };
  const POSTAL_FORMATS = {
    US: /^\d{5}$/,
    CA: /^[A-Z]\d[A-Z] ?\d[A-Z]\d$/i,
    SA: /^\d{5}$/,
  };
  const PROMO_CODES = { SAVE10: 0.1 };
  const EMAIL_FORMAT = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

  const lang = new URLSearchParams(window.location.search).get('lang') === 'ar' ? 'ar' : 'en';
  const strings = window.CHECKOUT_STRINGS;
  const t = (key, vars = {}) =>
    (strings[lang][key] ?? strings.en[key] ?? key).replace(/\{(\w+)\}/g, (_, name) => vars[name] ?? '');
  const currency = new Intl.NumberFormat(lang === 'ar' ? 'ar-SA-u-nu-latn' : 'en-US', {
    style: 'currency',
    currency: 'USD',
  });
  const formatMoney = (cents) => currency.format(cents / 100);

  const $ = (id) => document.getElementById(id);
  const els = {
    contactForm: $('contact-form'), name: $('full-name'), email: $('email'),
    shippingForm: $('shipping-form'), country: $('country'), postal: $('postal-code'),
    shippingBack: $('shipping-back'), shippingNext: $('shipping-continue'),
    summaryContact: $('summary-contact'), summaryShipping: $('summary-shipping'),
    promoInput: $('promo-code'), promoApply: $('promo-apply'), promoError: $('promo-error'),
    promoApplied: $('promo-applied'), promoBadge: $('promo-badge'), promoRemove: $('promo-remove'),
    orderError: $('order-error'), orderRetry: $('order-retry'),
    reviewBack: $('review-back'), placeOrder: $('place-order'),
    orderId: $('order-id'), confirmEmail: $('confirm-email'),
    cart: $('cart'), cartItems: $('cart-items'), subtotal: $('subtotal'),
    shippingCost: $('shipping-cost'), discountRow: $('discount-row'), discount: $('discount'),
    total: $('total'), langSwitch: $('lang-switch'),
  };

  const ui = { postalInvalid: false, submitting: false };
  const draft = loadDraft();

  // ---------------------------------------------------------------- draft --

  function emptyDraft() {
    return {
      step: 'contact',
      contact: { name: '', email: '' },
      shipping: { country: 'US', postal: '' },
      promo: null,
      discount: 0,
    };
  }

  function loadDraft() {
    const base = emptyDraft();
    try {
      const saved = JSON.parse(window.localStorage.getItem(STORAGE_KEY));
      if (!saved || typeof saved !== 'object') return base;
      const restored = {
        ...base,
        ...saved,
        contact: { ...base.contact, ...saved.contact },
        shipping: { ...base.shipping, ...saved.shipping },
      };
      if (!(restored.shipping.country in SHIPPING_RATES)) restored.shipping.country = 'US';
      return restored;
    } catch {
      return base;
    }
  }

  function saveDraft() {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(draft));
    } catch {
      // Storage can be unavailable (private mode, quota); the form still works.
    }
  }

  function clearDraft() {
    try {
      window.localStorage.removeItem(STORAGE_KEY);
    } catch {
      // Nothing to clear if storage is unavailable.
    }
  }

  // ----------------------------------------------------------- validation --

  const nameError = (value) => (value.trim() ? '' : 'errNameRequired');

  function emailError(value) {
    const email = value.trim();
    if (!email) return 'errEmailRequired';
    return EMAIL_FORMAT.test(email) ? '' : 'errEmailInvalid';
  }

  function postalError(country, value) {
    const postal = value.trim();
    if (!postal) return 'errPostalRequired';
    return POSTAL_FORMATS[country].test(postal) ? '' : `errPostal${country}`;
  }

  function normalizePostal(country, value) {
    const postal = value.trim().toUpperCase();
    return country === 'CA' ? postal.replace(/^(\w{3})\s*(\w{3})$/, '$1 $2') : postal;
  }

  function showFieldError(input, errorKey) {
    $(input.getAttribute('aria-describedby')).textContent = errorKey ? t(errorKey) : '';
    if (errorKey) input.setAttribute('aria-invalid', 'true');
    else input.removeAttribute('aria-invalid');
  }

  const hasVisibleError = (input) => input.getAttribute('aria-invalid') === 'true';

  function validateContact() {
    const nameKey = nameError(draft.contact.name);
    const emailKey = emailError(draft.contact.email);
    showFieldError(els.name, nameKey);
    showFieldError(els.email, emailKey);
    if (nameKey) els.name.focus();
    else if (emailKey) els.email.focus();
    return !nameKey && !emailKey;
  }

  function validatePostal() {
    const errorKey = postalError(draft.shipping.country, draft.shipping.postal);
    showFieldError(els.postal, errorKey);
    if (errorKey) ui.postalInvalid = true;
    els.shippingNext.disabled = ui.postalInvalid;
    return !errorKey;
  }

  // ------------------------------------------------------------ rendering --

  function el(tag, className, text) {
    const node = document.createElement(tag);
    node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function applyLanguage() {
    const root = document.documentElement;
    root.lang = lang;
    root.dir = lang === 'ar' ? 'rtl' : 'ltr';
    document.title = t('pageTitle');
    for (const node of document.querySelectorAll('[data-i18n]')) {
      node.textContent = t(node.dataset.i18n);
    }
    const other = lang === 'ar' ? 'en' : 'ar';
    els.langSwitch.textContent = t('switchLanguage');
    els.langSwitch.lang = other;
    els.langSwitch.hreflang = other;
    els.langSwitch.href = other === 'ar' ? '?lang=ar' : window.location.pathname;
  }

  function renderCart() {
    els.cartItems.replaceChildren(
      ...CART.map((item) => {
        const row = el('li', 'cart-item');
        row.dataset.sku = item.sku;
        row.append(
          el('span', 'cart-item-name', t(item.nameKey)),
          el('span', 'cart-item-qty', t('qty', { qty: item.qty })),
          el('span', 'cart-item-price', formatMoney(item.price * item.qty)),
        );
        return row;
      }),
    );
  }

  const cartSubtotal = () => CART.reduce((sum, item) => sum + item.price * item.qty, 0);

  function computeTotals() {
    const subtotal = cartSubtotal();
    const shipping = SHIPPING_RATES[draft.shipping.country];
    const discount = draft.discount;
    return { subtotal, shipping, discount, total: subtotal + shipping - discount };
  }

  function renderTotals() {
    const totals = computeTotals();
    els.subtotal.textContent = formatMoney(totals.subtotal);
    els.shippingCost.textContent = formatMoney(totals.shipping);
    els.discountRow.hidden = !draft.promo;
    els.discount.textContent = formatMoney(-totals.discount);
    els.total.textContent = formatMoney(totals.total);
  }

  function renderPromo() {
    const applied = Boolean(draft.promo);
    els.promoApplied.hidden = !applied;
    els.promoBadge.textContent = applied ? t('promoApplied', { code: draft.promo }) : '';
    els.promoInput.readOnly = applied;
    els.promoApply.disabled = applied;
    if (applied) els.promoInput.value = draft.promo;
  }

  function renderReview() {
    const { contact, shipping } = draft;
    els.summaryContact.textContent = `${contact.name.trim()}\n${contact.email.trim()}`;
    els.summaryShipping.textContent = `${t(`country${shipping.country}`)}\n${shipping.postal}`;
    renderPromo();
    renderTotals();
  }

  function showView(view, { moveFocus = true } = {}) {
    for (const panel of document.querySelectorAll('[data-view]')) {
      panel.hidden = panel.dataset.view !== view;
    }
    const current = STEPS.indexOf(view);
    for (const item of document.querySelectorAll('#steps li')) {
      const index = STEPS.indexOf(item.dataset.step);
      item.classList.toggle('done', current === -1 || index < current);
      if (index === current) item.setAttribute('aria-current', 'step');
      else item.removeAttribute('aria-current');
    }
    els.cart.hidden = view === 'confirmation';
    if (moveFocus) document.querySelector(`[data-view="${view}"] h2`).focus();
  }

  function goTo(step) {
    draft.step = step;
    saveDraft();
    if (step === 'review') renderReview();
    showView(step);
  }

  // --------------------------------------------------------------- promo --

  function applyPromo() {
    const code = els.promoInput.value.trim().toUpperCase();
    const rate = PROMO_CODES[code];
    if (!rate) {
      els.promoError.textContent = t(code ? 'errPromoInvalid' : 'errPromoRequired');
      return;
    }
    els.promoError.textContent = '';
    draft.promo = code;
    draft.discount = Math.round(cartSubtotal() * rate);
    saveDraft();
    renderPromo();
    renderTotals();
  }

  function removePromo() {
    draft.promo = null;
    els.promoInput.value = '';
    saveDraft();
    renderPromo();
    renderTotals();
    els.promoInput.focus();
  }

  // --------------------------------------------------------------- order --

  function orderPayload() {
    return {
      contact: { name: draft.contact.name.trim(), email: draft.contact.email.trim() },
      shipping: { ...draft.shipping },
      items: CART.map(({ sku, qty, price }) => ({ sku, qty, unit_price: price })),
      promo: draft.promo,
      totals: computeTotals(),
      currency: 'USD',
      locale: lang,
    };
  }

  async function placeOrder() {
    if (ui.submitting) return;
    ui.submitting = true;
    els.orderError.hidden = true;
    els.placeOrder.disabled = true;
    els.placeOrder.textContent = t('placing');
    try {
      const response = await fetch('/api/orders', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(orderPayload()),
      });
      if (response.status !== 201) throw new Error(`Order request failed: HTTP ${response.status}`);
      const { order_id: orderId } = await response.json();
      if (!orderId) throw new Error('Order response did not include an order id');
      showConfirmation(orderId);
    } catch (error) {
      console.warn(error);
      els.orderError.hidden = false;
      els.orderRetry.focus();
    } finally {
      ui.submitting = false;
      els.placeOrder.disabled = false;
      els.placeOrder.textContent = t('placeOrder');
    }
  }

  function showConfirmation(orderId) {
    els.orderId.textContent = orderId;
    els.confirmEmail.textContent = draft.contact.email.trim();
    clearDraft();
    showView('confirmation');
  }

  // -------------------------------------------------------------- events --

  function bindInput(input, update, revalidate) {
    input.addEventListener('input', () => {
      update(input.value);
      saveDraft();
      if (hasVisibleError(input)) revalidate();
    });
  }

  bindInput(els.name, (value) => { draft.contact.name = value; },
    () => showFieldError(els.name, nameError(draft.contact.name)));
  bindInput(els.email, (value) => { draft.contact.email = value; },
    () => showFieldError(els.email, emailError(draft.contact.email)));
  bindInput(els.postal, (value) => { draft.shipping.postal = value; }, validatePostal);

  els.email.addEventListener('change', () => {
    if (draft.contact.email.trim()) showFieldError(els.email, emailError(draft.contact.email));
  });
  els.postal.addEventListener('change', () => {
    if (draft.shipping.postal.trim()) validatePostal();
  });
  els.country.addEventListener('change', () => {
    draft.shipping.country = els.country.value;
    saveDraft();
    renderTotals();
    if (draft.shipping.postal.trim()) validatePostal();
  });

  els.contactForm.addEventListener('submit', (event) => {
    event.preventDefault();
    if (validateContact()) goTo('shipping');
  });

  els.shippingForm.addEventListener('submit', (event) => {
    event.preventDefault();
    if (!validatePostal()) {
      els.postal.focus();
      return;
    }
    draft.shipping.postal = normalizePostal(draft.shipping.country, draft.shipping.postal);
    els.postal.value = draft.shipping.postal;
    goTo('review');
  });

  els.shippingBack.addEventListener('click', () => goTo('contact'));
  els.reviewBack.addEventListener('click', () => goTo('shipping'));
  els.promoApply.addEventListener('click', applyPromo);
  els.promoRemove.addEventListener('click', removePromo);
  els.promoInput.addEventListener('input', () => { els.promoError.textContent = ''; });
  els.promoInput.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') {
      event.preventDefault();
      applyPromo();
    }
  });
  els.placeOrder.addEventListener('click', placeOrder);
  els.orderRetry.addEventListener('click', placeOrder);

  // ---------------------------------------------------------------- init --

  function resumeStep() {
    // Never resume past a step whose data is incomplete.
    if (nameError(draft.contact.name) || emailError(draft.contact.email)) return 'contact';
    if (draft.step === 'review' && postalError(draft.shipping.country, draft.shipping.postal)) {
      return 'shipping';
    }
    return STEPS.includes(draft.step) ? draft.step : 'contact';
  }

  applyLanguage();
  renderCart();
  els.name.value = draft.contact.name;
  els.email.value = draft.contact.email;
  els.country.value = draft.shipping.country;
  els.postal.value = draft.shipping.postal;
  renderTotals();
  draft.step = resumeStep();
  if (draft.step === 'review') renderReview();
  showView(draft.step, { moveFocus: false });
})();
