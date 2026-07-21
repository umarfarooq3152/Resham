export interface ShoppingIntent {
  category: string | null;
  color: string | null;
  size: string | null;
  fit: string | null;
  priceMax: number | null;
  priceMin: number | null;
  descriptive: string | null;
  occasion: string | null;
  tradition: 'eastern' | 'western' | 'fusion' | null;
  audience: 'men' | 'women' | null;
  wantsKids: boolean | null;
  childAgeMonths: number | null;
}
/** A purchasable Shopify variant, for the cart/add.js hand-off — Resham has
 * no checkout of its own, so this is the real merchant variant id, distinct
 * from ProductResult.id (Resham's own catalog key). */
export interface ProductVariant {
  variantId: string;
  color: string | null;
  size: string | null;
  available: boolean;
}

export interface ProductResult {
  id: string;
  title: string;
  price: number;
  currency: string;
  imageUrl: string;
  productUrl: string;
  score: number;
  reason: string;
  matchDetails?: {
    colors: string[];
    sizes: string[];
    fit: string | null;
    occasion: string | null;
    audience: string | null;
    imageMatchesColor: boolean | null;
  };
  variants: ProductVariant[];
}

export interface SearchResult {
  intent: ShoppingIntent;
  products: ProductResult[];
  notice: string | null;
  meta: {
    storeDomain: string;
    fetchedCount: number;
    mappedCount: number;
    exactCount: number;
    catalogCapped: boolean;
    relaxed: boolean;
    relaxedFilters: string[];
    durationMs: number;
  };
}

export type ErrorCode =
  | 'UNSUPPORTED_PAGE'
  | 'UNSUPPORTED_STORE'
  | 'MIC_PERMISSION_DENIED'
  | 'EMPTY_AUDIO'
  | 'AUDIO_TOO_LARGE'
  | 'TRANSCRIPTION_FAILED'
  | 'EMPTY_INTENT'
  | 'CATALOG_UNAVAILABLE'
  | 'CATALOG_TIMEOUT'
  | 'RATE_LIMITED'
  | 'PROVIDER_UNAVAILABLE'
  | 'NO_MATCHES'
  | 'REQUEST_CANCELLED'
  | 'CART_ADD_FAILED'
  | 'INTERNAL_ERROR';

export interface ExtensionError {
  code: ErrorCode;
  message: string;
  retriable: boolean;
}

export type WorkerRequest =
  | { type: 'GET_ACTIVE_STORE' }
  | { type: 'SEARCH_PRODUCTS'; requestId: string; query: string; previousIntent?: ShoppingIntent | null }
  | { type: 'CANCEL_SEARCH'; requestId: string }
  | { type: 'OPEN_PRODUCT'; productUrl: string }
  | { type: 'ADD_TO_CART'; variantId: string; quantity: number };

export type WorkerResponse =
  | { ok: true; data: SearchResult }
  | { ok: true; store: { name: string; domain: string } }
  | { ok: true; cancelled: true }
  | { ok: true; opened: true }
  | { ok: true; added: true }
  | { ok: false; error: ExtensionError };

/** Popup/background <-> injected content-script channel — separate from
 * WorkerRequest/WorkerResponse above (popup <-> background only). Only
 * fires on an explicit "Add to Cart" click; see extension/README.md's
 * "Data and permissions" section for the full scope of what this touches. */
export type ContentScriptMessage = {
  type: 'CART_ADD';
  variantId: string;
  quantity: number;
};

export type ContentScriptResponse =
  | { ok: true }
  | { ok: false; error: string };

export interface SessionSnapshot {
  requestId: string;
  query: string;
  stage: 'searching' | 'results' | 'error';
  result?: SearchResult;
  error?: ExtensionError;
  updatedAt: number;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  text: string;
}

export interface ConversationState {
  messages: ChatMessage[];
  currentResult: SearchResult | null;
  lastQuery: string;
  updatedAt: number;
}
