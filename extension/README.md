# Resham Chrome Extension

Chrome MV3 shopping workspace for natural-language search on the current
Shopify store represented in Resham's crawled brand catalog. Products stay on
the left while a persistent chat on the right carries the current intent
through follow-up refinements.

## Development

1. Start the Resham FastAPI backend at `http://localhost:8000` with
   `GROQ_API_KEY` configured in the repository `.env`.
2. Run `npm install`, then `npm run build` in this directory.
3. Load `extension/dist` from `chrome://extensions` in Developer mode.
4. Open an HTTPS page on a crawled brand domain and click the extension action.

Useful checks:

```bash
npm run typecheck
npm test
npm run test:e2e
npm run build
```

The E2E test launches an unpacked extension using Playwright's full Chromium
channel. It may need to run outside a restricted process sandbox.

## Deployment configuration

`src/config.ts` and `manifest.json` intentionally point to the local backend.
Change the API base URL, `host_permissions`, and CSP `connect-src` together when
deploying. Never add Groq to host permissions and never bundle a Groq key.

The extension accepts HTTPS store origins, while the backend authoritatively
validates the domain against active rows in the `brands` table. Adding a crawled
brand therefore requires no client release.

## Data and permissions

- `activeTab`: reads the current tab URL only after the user opens the popup.
- `storage`: keeps the current in-flight/result state in session storage so a
  text search can be recovered when the popup reopens.
- `scripting`: lets the background worker inject a small script into the
  active tab — used **only** for "Add to Cart" (see below), scoped by
  `activeTab`'s temporary per-invocation grant, not a standing broad host
  permission.
- Backend host permission: transcription and search API requests only.
- No accounts, no browsing history access, no persistent DOM observation.

### Add to Cart

Resham has no checkout of its own — every crawled brand is a separate
Shopify store with its own cart. Clicking "Add to Cart" on a product:

1. Injects `cartAdd.js` into the active tab (already on that brand's own
   storefront, per the extension's existing design) via
   `chrome.scripting.executeScript`, triggered only by that click.
2. Sends it exactly one same-origin `fetch('/cart/add.js', ...)` — Shopify's
   standard, theme-independent Ajax cart endpoint. This is a normal
   same-origin page request: the browser attaches the shopper's existing
   session cookie automatically, and this code never reads or stores that
   cookie's value.
3. Reports success/failure back in the popup.

This does not persist, observe, or modify the page beyond that one request,
and does not run on page load — only on an explicit click. It also does not
update the store's own on-page cart badge (that's theme-specific JS this
extension doesn't chase); the popup's own confirmation is the signal, and
completing checkout happens on the merchant's own site as normal.

Microphone audio is recorded only while the popup remains open, sent to the
backend/Groq for transcription, and not stored by Resham. Merchant product
images load remotely with `referrerpolicy="no-referrer"`.
