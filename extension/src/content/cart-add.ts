/**
 * Injected only on an explicit "Add to Cart" click (see background.ts's
 * ADD_TO_CART handler) — never runs on page load, never observes or
 * modifies the page otherwise. Built as a plain IIFE, not ESM: MV3 content
 * scripts injected via chrome.scripting.executeScript's `files` option
 * don't support top-level ESM (see build.mjs's separate `format: 'iife'`
 * entry for this file).
 *
 * Fires exactly one same-origin POST to the store's own /cart/add.js —
 * Shopify's standard, theme-independent Ajax cart endpoint. Runs in the
 * page's own origin, so the shopper's existing session cookie rides along
 * automatically; this script never reads or touches the cookie itself.
 */

import type { ContentScriptMessage, ContentScriptResponse } from '../shared/contracts';

async function addToCart(variantId: string, quantity: number): Promise<ContentScriptResponse> {
  try {
    const response = await fetch('/cart/add.js', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify({ id: variantId, quantity }),
    });
    if (!response.ok) {
      const detail = await response.json().catch(() => null);
      const message = detail && typeof detail === 'object' && 'description' in detail
        ? String((detail as { description: unknown }).description)
        : `cart/add.js returned ${response.status}`;
      return { ok: false, error: message };
    }
    return { ok: true };
  } catch (error) {
    return { ok: false, error: error instanceof Error ? error.message : 'Network error' };
  }
}

chrome.runtime.onMessage.addListener(
  (message: ContentScriptMessage, _sender, sendResponse: (response: ContentScriptResponse) => void) => {
    if (message.type !== 'CART_ADD') return false;
    void addToCart(message.variantId, message.quantity).then(sendResponse);
    return true;
  },
);
