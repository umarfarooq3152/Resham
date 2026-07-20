import type { ProductResult, ProductVariant, WorkerRequest, WorkerResponse } from '../shared/contracts';

function formatPrice(price: number, currency: string): string {
  if (currency === 'PKR') return `Rs. ${Math.round(price).toLocaleString('en-PK')}`;
  return `${currency} ${price.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
}
const LOWER_BODY_PRODUCT = /\b(?:jeans?|pants?|trousers?|chinos?|joggers?|leggings?|shorts?|skirts?|skorts?|culottes?|shalwars?|bottoms?)\b/i;

export function usesLowerImageFocus(title: string): boolean {
  return LOWER_BODY_PRODUCT.test(title);
}

function externalLinkIcon(): SVGSVGElement {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('aria-hidden', 'true');
  svg.classList.add('card-link-icon');
  const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
  path.setAttribute('d', 'M14 5h5v5M19 5l-9 9M19 13v5a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h5');
  path.setAttribute('fill', 'none');
  path.setAttribute('stroke', 'currentColor');
  path.setAttribute('stroke-width', '1.8');
  path.setAttribute('stroke-linecap', 'round');
  path.setAttribute('stroke-linejoin', 'round');
  svg.append(path);
  return svg;
}

function variantLabel(variant: ProductVariant): string {
  return [variant.color, variant.size].filter(Boolean).join(' / ') || 'Select option';
}

/** Cart control: no button at all when there's nothing purchasable to add
 * (variants missing/all unavailable — degrades gracefully rather than
 * offering a control that can only fail), a single "Add to Cart" button
 * for one variant, or a compact <select> + button for several. Resham has
 * no checkout of its own — success hands off to the merchant's own cart on
 * their site, it does not update this popup's or the page's own cart badge
 * (see extension/README.md). */
function renderCartControl(
  product: ProductResult,
  sendMessage: (message: WorkerRequest) => Promise<unknown>,
): HTMLElement | null {
  const available = product.variants.filter((v) => v.available);
  if (available.length === 0) return null;

  const wrapper = document.createElement('span');
  wrapper.className = 'cart-control';

  let select: HTMLSelectElement | null = null;
  if (available.length > 1) {
    select = document.createElement('select');
    select.className = 'cart-variant-select';
    select.setAttribute('aria-label', `Choose an option for ${product.title}`);
    for (const variant of available) {
      const option = document.createElement('option');
      option.value = variant.variantId;
      option.textContent = variantLabel(variant);
      select.append(option);
    }
    select.addEventListener('click', (e) => e.stopPropagation());
    wrapper.append(select);
  }

  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'cart-add-button';
  button.textContent = 'Add to Cart';

  const status = document.createElement('span');
  status.className = 'cart-status';
  status.hidden = true;

  button.addEventListener('click', (e) => {
    e.stopPropagation();
    const variantId = select ? select.value : available[0].variantId;
    button.disabled = true;
    status.hidden = true;
    void sendMessage({ type: 'ADD_TO_CART', variantId, quantity: 1 })
      .then((response) => {
        const result = response as WorkerResponse;
        status.hidden = false;
        if (result.ok) {
          status.textContent = 'Added — visit your cart on this site to check out.';
          status.classList.remove('is-error');
        } else {
          status.textContent = result.error.message;
          status.classList.add('is-error');
        }
      })
      .finally(() => {
        button.disabled = false;
      });
  });

  wrapper.append(button, status);
  return wrapper;
}

export function renderProductCard(
  product: ProductResult,
  index: number,
  sendMessage: (message: WorkerRequest) => Promise<unknown>,
): HTMLDivElement {
  // A <div role="button"> for the card, not a real <button> — a real
  // "Add to Cart" <button>/<select> below must nest inside it, and
  // interactive elements cannot nest inside a <button> in valid HTML.
  const card = document.createElement('div');
  card.className = 'product-card';
  card.setAttribute('role', 'button');
  card.setAttribute('tabindex', '0');
  card.setAttribute('aria-label', `${product.title}, ${formatPrice(product.price, product.currency)}. Opens in a new tab.`);

  const media = document.createElement('span');
  media.className = 'product-media';
  if (usesLowerImageFocus(product.title)) media.classList.add('is-lower-body');
  const fallback = document.createElement('span');
  fallback.className = 'image-fallback';
  fallback.textContent = 'Image unavailable';
  const image = document.createElement('img');
  image.src = product.imageUrl;
  image.alt = '';
  image.loading = 'lazy';
  image.referrerPolicy = 'no-referrer';
  image.addEventListener('error', () => {
    image.hidden = true;
    fallback.classList.add('is-visible');
  }, { once: true });
  media.append(image, fallback);

  const body = document.createElement('span');
  body.className = 'product-body';
  if (index === 0) {
    const badge = document.createElement('span');
    badge.className = 'best-match';
    badge.textContent = 'Best match';
    body.append(badge);
  }
  const title = document.createElement('span');
  title.className = 'product-title';
  title.textContent = product.title;
  const price = document.createElement('span');
  price.className = 'product-price';
  price.textContent = formatPrice(product.price, product.currency);
  const verifiedFacts = document.createElement('span');
  verifiedFacts.className = 'verified-facts';
  const factLabels = [
    ...(product.matchDetails?.colors || []),
    ...(product.matchDetails?.sizes || []).map((size) => `Size ${size}`),
    product.matchDetails?.fit ? `${product.matchDetails.fit} fit` : null,
    product.matchDetails?.occasion || null,
  ].filter((value): value is string => Boolean(value));
  verifiedFacts.textContent = factLabels.join(' · ');
  verifiedFacts.hidden = factLabels.length === 0;
  const imageNotice = document.createElement('span');
  imageNotice.className = 'image-color-notice';
  imageNotice.textContent = product.matchDetails?.imageMatchesColor === false
    ? 'Requested color is available; preview image may differ.'
    : '';
  imageNotice.hidden = product.matchDetails?.imageMatchesColor !== false;
  const reasonLabel = document.createElement('span');
  reasonLabel.className = 'reason-label';
  reasonLabel.textContent = 'Why it matches';
  const reason = document.createElement('span');
  reason.className = 'product-reason';
  reason.textContent = product.reason;
  body.append(title, price, verifiedFacts, imageNotice, reasonLabel, reason);

  const cartControl = renderCartControl(product, sendMessage);
  if (cartControl) body.append(cartControl);

  card.append(media, body, externalLinkIcon());
  const openProduct = () => {
    void sendMessage({ type: 'OPEN_PRODUCT', productUrl: product.productUrl });
  };
  card.addEventListener('click', openProduct);
  card.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      openProduct();
    }
  });
  return card;
}
