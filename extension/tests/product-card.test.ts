import { describe, expect, it, vi } from 'vitest';

import { renderProductCard } from '../src/ui/product-card';

describe('product card', () => {
  it('renders fetched strings as text and sends a safe open request', async () => {
    const send = vi.fn().mockResolvedValue({ ok: true });
    const card = renderProductCard({
      id: '1',
      title: '<img src=x onerror=alert(1)> Core Shirt',
      price: 2999,
      currency: 'PKR',
      imageUrl: 'https://cdn.example.com/1.jpg',
      productUrl: 'https://outfitters.com.pk/products/core-shirt',
      score: 9,
      reason: '<script>bad()</script> Clean casual metadata.',
      variants: [],
    }, 0, send);

    document.body.append(card);
    expect(card.querySelectorAll('script')).toHaveLength(0);
    expect(card.querySelector('.product-title')?.textContent).toContain('<img');
    expect(card.querySelector('.product-reason')?.textContent).toContain('<script>');
    expect(card.textContent).toContain('Best match');
    card.click();
    expect(send).toHaveBeenCalledWith({
      type: 'OPEN_PRODUCT',
      productUrl: 'https://outfitters.com.pk/products/core-shirt',
    });
  });

  it('uses an accessible external-tab label', () => {
    const card = renderProductCard({
      id: '2', title: 'Olive Shirt', price: 2500, currency: 'PKR',
      imageUrl: 'https://cdn.example.com/2.jpg',
      productUrl: 'https://outfitters.com.pk/products/olive-shirt',
      score: 8, reason: 'Olive metadata supports an earthy look.',
      variants: [],
    }, 1, vi.fn());
    expect(card.getAttribute('aria-label')).toContain('Opens in a new tab');
    expect(card.textContent).not.toContain('Best match');
  });

  it('focuses lower in catalog images for lower-body garments', () => {
    const pants = renderProductCard({
      id: '3', title: 'Relaxed Fit Trousers', price: 3500, currency: 'PKR',
      imageUrl: 'https://cdn.example.com/3.jpg',
      productUrl: 'https://outfitters.com.pk/products/relaxed-trousers',
      score: 9, reason: 'Matches trousers.',
      variants: [],
    }, 2, vi.fn());
    const shirt = renderProductCard({
      id: '4', title: 'Oxford Shirt', price: 3000, currency: 'PKR',
      imageUrl: 'https://cdn.example.com/4.jpg',
      productUrl: 'https://outfitters.com.pk/products/oxford-shirt',
      score: 9, reason: 'Matches shirt.',
      variants: [],
    }, 3, vi.fn());

    expect(pants.querySelector('.product-media')?.classList).toContain('is-lower-body');
    expect(shirt.querySelector('.product-media')?.classList).not.toContain('is-lower-body');
  });

  it('shows verified facts and warns when the preview is not color-specific', () => {
    const card = renderProductCard({
      id: '5', title: 'Baggy Jeans', price: 4500, currency: 'PKR',
      imageUrl: 'https://cdn.example.com/generic.jpg',
      productUrl: 'https://outfitters.com.pk/products/baggy-jeans',
      score: 10, reason: 'Matches the requested details.',
      matchDetails: {
        colors: ['Black'], sizes: ['32'], fit: 'baggy', occasion: null,
        audience: 'men', imageMatchesColor: false,
      },
      variants: [],
    }, 0, vi.fn());

    expect(card.querySelector('.verified-facts')?.textContent).toContain('Black');
    expect(card.querySelector('.verified-facts')?.textContent).toContain('baggy fit');
    expect(card.querySelector('.image-color-notice')?.textContent).toContain('preview image may differ');
  });

  describe('cart control', () => {
    it('renders no cart control when there are no purchasable variants', () => {
      const card = renderProductCard({
        id: '6', title: 'Sold Out Kurta', price: 3000, currency: 'PKR',
        imageUrl: 'https://cdn.example.com/6.jpg',
        productUrl: 'https://outfitters.com.pk/products/sold-out-kurta',
        score: 7, reason: 'Matches kurta.',
        variants: [{ variantId: 'v1', color: 'Blue', size: 'M', available: false }],
      }, 0, vi.fn());

      expect(card.querySelector('.cart-control')).toBeNull();
    });

    it('adds the single available variant directly, with no picker, on click', async () => {
      const send = vi.fn().mockResolvedValue({ ok: true, added: true });
      const card = renderProductCard({
        id: '7', title: 'Blue Kurta', price: 3000, currency: 'PKR',
        imageUrl: 'https://cdn.example.com/7.jpg',
        productUrl: 'https://outfitters.com.pk/products/blue-kurta',
        score: 9, reason: 'Matches kurta.',
        variants: [{ variantId: 'v42', color: 'Blue', size: 'M', available: true }],
      }, 0, send);
      document.body.append(card);

      expect(card.querySelector('.cart-variant-select')).toBeNull();
      const button = card.querySelector<HTMLButtonElement>('.cart-add-button');
      expect(button).not.toBeNull();
      button!.click();
      await Promise.resolve();

      expect(send).toHaveBeenCalledWith({ type: 'ADD_TO_CART', variantId: 'v42', quantity: 1 });
    });

    it('offers a picker and uses the selected variant when several are available', async () => {
      const send = vi.fn().mockResolvedValue({ ok: true, added: true });
      const card = renderProductCard({
        id: '8', title: 'Kurta', price: 3000, currency: 'PKR',
        imageUrl: 'https://cdn.example.com/8.jpg',
        productUrl: 'https://outfitters.com.pk/products/kurta',
        score: 9, reason: 'Matches kurta.',
        variants: [
          { variantId: 'v1', color: 'Blue', size: 'M', available: true },
          { variantId: 'v2', color: 'Blue', size: 'L', available: true },
          { variantId: 'v3', color: 'Red', size: 'S', available: false },
        ],
      }, 0, send);
      document.body.append(card);

      const select = card.querySelector<HTMLSelectElement>('.cart-variant-select');
      expect(select).not.toBeNull();
      // Unavailable variants are never offered as choices.
      expect(select!.options.length).toBe(2);
      select!.value = 'v2';

      card.querySelector<HTMLButtonElement>('.cart-add-button')!.click();
      await Promise.resolve();

      expect(send).toHaveBeenCalledWith({ type: 'ADD_TO_CART', variantId: 'v2', quantity: 1 });
    });

    it('clicking the cart control never triggers the card-level OPEN_PRODUCT navigation', async () => {
      const send = vi.fn().mockResolvedValue({ ok: true, added: true });
      const card = renderProductCard({
        id: '9', title: 'Kurta', price: 3000, currency: 'PKR',
        imageUrl: 'https://cdn.example.com/9.jpg',
        productUrl: 'https://outfitters.com.pk/products/kurta',
        score: 9, reason: 'Matches kurta.',
        variants: [{ variantId: 'v1', color: 'Blue', size: 'M', available: true }],
      }, 0, send);
      document.body.append(card);

      card.querySelector<HTMLButtonElement>('.cart-add-button')!.click();
      await Promise.resolve();

      expect(send).toHaveBeenCalledTimes(1);
      expect(send).not.toHaveBeenCalledWith(expect.objectContaining({ type: 'OPEN_PRODUCT' }));
    });

    it('shows the error message inline when the cart add fails', async () => {
      const send = vi.fn().mockResolvedValue({
        ok: false,
        error: { code: 'CART_ADD_FAILED', message: 'Out of stock', retriable: true },
      });
      const card = renderProductCard({
        id: '10', title: 'Kurta', price: 3000, currency: 'PKR',
        imageUrl: 'https://cdn.example.com/10.jpg',
        productUrl: 'https://outfitters.com.pk/products/kurta',
        score: 9, reason: 'Matches kurta.',
        variants: [{ variantId: 'v1', color: 'Blue', size: 'M', available: true }],
      }, 0, send);
      document.body.append(card);

      card.querySelector<HTMLButtonElement>('.cart-add-button')!.click();
      await Promise.resolve();
      await Promise.resolve();

      const status = card.querySelector('.cart-status');
      expect(status?.textContent).toContain('Out of stock');
      expect(status?.classList.contains('is-error')).toBe(true);
    });
  });
});
