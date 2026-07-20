import { API_BASE_URL, SEARCH_TIMEOUT_MS, SESSION_KEY } from './config';
import type {
  ContentScriptMessage,
  ContentScriptResponse,
  SearchResult,
  SessionSnapshot,
  ShoppingIntent,
  WorkerRequest,
  WorkerResponse,
} from './shared/contracts';
import { createError, getSupportedStore, isSafeProductUrl, normalizeBackendError } from './shared/validators';

const activeRequests = new Map<string, AbortController>();

async function activeTab(): Promise<chrome.tabs.Tab> {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab) throw createError('UNSUPPORTED_PAGE', 'No active browser tab was found.');
  return tab;
}

async function saveSnapshot(snapshot: SessionSnapshot): Promise<void> {
  await chrome.storage.session.set({ [SESSION_KEY]: snapshot });
}

async function searchProducts(
  requestId: string,
  query: string,
  previousIntent?: ShoppingIntent | null,
): Promise<WorkerResponse> {
  const trimmed = query.trim();
  if (!trimmed) {
    return { ok: false, error: createError('EMPTY_INTENT', 'Describe what you want to find first.') };
  }

  try {
    const store = getSupportedStore((await activeTab()).url);
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort('timeout'), SEARCH_TIMEOUT_MS);
    activeRequests.set(requestId, controller);
    await saveSnapshot({ requestId, query: trimmed, stage: 'searching', updatedAt: Date.now() });

    try {
      const response = await fetch(`${API_BASE_URL}/extension/search`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: trimmed,
          storeOrigin: store.origin,
          previousIntent: previousIntent || null,
        }),
        signal: controller.signal,
      });
      const payload: unknown = await response.json().catch(() => ({}));
      if (!response.ok) {
        const error = normalizeBackendError(response.status, payload);
        await saveSnapshot({ requestId, query: trimmed, stage: 'error', error, updatedAt: Date.now() });
        return { ok: false, error };
      }
      const result = payload as SearchResult;
      await saveSnapshot({ requestId, query: trimmed, stage: 'results', result, updatedAt: Date.now() });
      return { ok: true, data: result };
    } catch (error) {
      const cancelled = controller.signal.aborted;
      const extensionError = cancelled
        ? createError(controller.signal.reason === 'timeout' ? 'CATALOG_TIMEOUT' : 'REQUEST_CANCELLED', controller.signal.reason === 'timeout' ? 'The search took too long. Please try again.' : 'Search cancelled.', controller.signal.reason === 'timeout')
        : createError(
          'PROVIDER_UNAVAILABLE',
          API_BASE_URL.includes('localhost')
            ? 'The local Resham service is not running. Start the backend on port 8000, then retry.'
            : 'Resham could not reach the matching service. Check your connection, then retry.',
          true,
        );
      await saveSnapshot({ requestId, query: trimmed, stage: 'error', error: extensionError, updatedAt: Date.now() });
      return { ok: false, error: extensionError };
    } finally {
      clearTimeout(timeout);
      activeRequests.delete(requestId);
    }
  } catch (error) {
    const extensionError = error && typeof error === 'object' && 'code' in error
      ? error as ReturnType<typeof createError>
      : createError('INTERNAL_ERROR', 'The active store could not be checked.');
    return { ok: false, error: extensionError };
  }
}

async function addToCart(variantId: string, quantity: number): Promise<WorkerResponse> {
  try {
    const tab = await activeTab();
    // getSupportedStore also confirms https + a real hostname before we
    // ever inject anything into the tab.
    getSupportedStore(tab.url);
    if (tab.id === undefined) {
      return { ok: false, error: createError('CART_ADD_FAILED', 'No active tab to add this to.') };
    }

    // Safe to call on every add — re-injecting an already-injected script
    // is a no-op, not a duplicate listener (the listener replaces itself).
    await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ['cartAdd.js'] });

    const response = (await chrome.tabs.sendMessage(tab.id, {
      type: 'CART_ADD',
      variantId,
      quantity,
    } satisfies ContentScriptMessage)) as ContentScriptResponse;

    if (!response.ok) {
      return { ok: false, error: createError('CART_ADD_FAILED', response.error, true) };
    }
    return { ok: true, added: true };
  } catch (error) {
    const extensionError = error && typeof error === 'object' && 'code' in error
      ? error as ReturnType<typeof createError>
      : createError('CART_ADD_FAILED', 'Could not add that to your cart on this page.', true);
    return { ok: false, error: extensionError };
  }
}

async function handleMessage(message: WorkerRequest): Promise<WorkerResponse> {
  if (message.type === 'GET_ACTIVE_STORE') {
    try {
      const store = getSupportedStore((await activeTab()).url);
      return { ok: true, store: { name: store.name, domain: store.domain } };
    } catch (error) {
      return { ok: false, error: error as ReturnType<typeof createError> };
    }
  }
  if (message.type === 'SEARCH_PRODUCTS') {
    return searchProducts(message.requestId, message.query, message.previousIntent);
  }
  if (message.type === 'CANCEL_SEARCH') {
    activeRequests.get(message.requestId)?.abort('cancelled');
    return { ok: true, cancelled: true };
  }
  if (message.type === 'OPEN_PRODUCT') {
    if (!isSafeProductUrl(message.productUrl)) {
      return { ok: false, error: createError('INTERNAL_ERROR', 'That product link was not safe to open.') };
    }
    await chrome.tabs.create({ url: message.productUrl });
    return { ok: true, opened: true };
  }
  if (message.type === 'ADD_TO_CART') {
    return addToCart(message.variantId, message.quantity);
  }
  return { ok: false, error: createError('INTERNAL_ERROR', 'Unknown extension message.') };
}

chrome.runtime.onMessage.addListener((message: WorkerRequest, sender, sendResponse) => {
  if (sender.id !== chrome.runtime.id) {
    sendResponse({ ok: false, error: createError('INTERNAL_ERROR', 'Untrusted message sender.') });
    return false;
  }
  void handleMessage(message).then(sendResponse);
  return true;
});
