import { useCallback, useEffect, useRef, useState } from 'react';
import { resetSession as resetSessionApi, sendSessionMessage } from '../api/session';
import { searchProducts } from '../api/products';
import { FilterChips, Message, Product, SessionState } from '../types';

const DEFAULT_FILTERS: FilterChips = {
  style: 'All Styles',
  occasion: 'All Occasions',
  budget: 'All Budgets',
};

// Bump when server-side intent/session semantics change so an evaluator never
// rehydrates a stale, polluted conversation from an older build.
const CHAT_SNAPSHOT_KEY = 'dhaaga-chat-snapshot-v3';
const MIN_RESPONSE_TRANSITION_MS = 900;

interface ChatSnapshot {
  entryQuery: string;
  sessionId: string | null;
  messages: Message[];
  products: Product[];
  totalResults?: number;
  filters: FilterChips;
  sessionState: SessionState | null;
}

function loadSnapshot(): ChatSnapshot | null {
  try {
    const raw = localStorage.getItem(CHAT_SNAPSHOT_KEY)
      ?? sessionStorage.getItem(CHAT_SNAPSHOT_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as ChatSnapshot;
  } catch {
    return null;
  }
}

function nowStr(): string {
  return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

let messageIdCounter = 0;
function nextMessageId(prefix: string): string {
  // Date.now() alone can collide when two messages are created in the same
  // millisecond (e.g. React StrictMode's double-invoked effects in dev) —
  // a monotonic counter guarantees uniqueness regardless of timing.
  messageIdCounter += 1;
  return `${prefix}-${Date.now()}-${messageIdCounter}`;
}

/** DiscoveryScreen's quick-filter chips route into this same chat pipeline
 * (matching the existing screen-transition flow) by composing a natural
 * language message from the selected filters. */
function composeInitialQuery(
  query?: string,
  filters?: { style?: string; occasion?: string; budget?: string }
): string {
  if (query && query.trim()) return query;

  const parts: string[] = [];
  if (filters?.style) parts.push(filters.style);
  if (filters?.occasion) parts.push(`for ${filters.occasion}`);
  if (filters?.budget) parts.push(filters.budget);
  return parts.length > 0 ? `Show me ${parts.join(', ')}` : '';
}

interface UseSessionChatResult {
  messages: Message[];
  filteredProducts: Product[];
  totalResults: number;
  filters: FilterChips;
  isChatLoading: boolean;
  isProductsLoading: boolean;
  isLoadingMore: boolean;
  hasMoreResults: boolean;
  sendMessage: (text: string) => void;
  loadMore: () => void;
  resetSession: () => void;
}

function buildPaginationQuery(state: SessionState | null): Parameters<typeof searchProducts>[0] {
  return {
    q: state?.semantic_query || undefined,
    category: state?.category || undefined,
    department:
      state?.department === 'men' || state?.department === 'women' || state?.department === 'unisex'
        ? state.department
        : undefined,
    occasion: state?.occasion || undefined,
    color: state?.color_preference || undefined,
    size: state?.size || undefined,
    tags: state?.style_descriptors?.length ? state.style_descriptors : undefined,
    wantsKids: Boolean(state?.wants_kids),
    childAgeMonths: state?.child_age_months ?? undefined,
    maxPrice: state?.budget_max ?? undefined,
  };
}

export function useSessionChat(
  userName: string,
  department?: 'men' | 'women',
  initialQuery?: string,
  initialFilters?: { style?: string; occasion?: string; budget?: string }
): UseSessionChatResult {
  const entryQuery = composeInitialQuery(initialQuery, initialFilters);
  const initialSnapshotRef = useRef<ChatSnapshot | null>(loadSnapshot());
  const sessionIdRef = useRef<string | null>(initialSnapshotRef.current?.sessionId ?? null);
  const sessionStateRef = useRef<SessionState | null>(initialSnapshotRef.current?.sessionState ?? null);
  const hasTriggeredInitialRef = useRef(
    initialSnapshotRef.current !== null
      && (!entryQuery || initialSnapshotRef.current.entryQuery === entryQuery)
  );
  const [messages, setMessages] = useState<Message[]>(initialSnapshotRef.current?.messages ?? []);
  const [filteredProducts, setFilteredProducts] = useState<Product[]>(initialSnapshotRef.current?.products ?? []);
  const [totalResults, setTotalResults] = useState(
    initialSnapshotRef.current?.totalResults ?? initialSnapshotRef.current?.products.length ?? 0
  );
  const [filters, setFilters] = useState<FilterChips>(initialSnapshotRef.current?.filters ?? DEFAULT_FILTERS);
  const [isChatLoading, setIsChatLoading] = useState(false);
  const [isProductsLoading, setIsProductsLoading] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [hasMoreResults, setHasMoreResults] = useState(
    Boolean(initialSnapshotRef.current && (initialSnapshotRef.current.totalResults ?? 0) > initialSnapshotRef.current.products.length)
  );
  const pageRef = useRef(Math.max(1, Math.ceil((initialSnapshotRef.current?.products.length ?? 0) / 40)));
  const requestInFlightRef = useRef(false);

  const sendMessage = useCallback((text: string) => {
    if (!text.trim() || requestInFlightRef.current) return;
    requestInFlightRef.current = true;

    const userMessage: Message = {
      id: nextMessageId('user'),
      sender: 'user',
      text,
      timestamp: nowStr(),
    };
    setMessages((prev) => [...prev, userMessage]);
    setIsChatLoading(true);
    setIsProductsLoading(true);

    Promise.all([
      sendSessionMessage(sessionIdRef.current, text, department, sessionStateRef.current),
      new Promise<void>((resolve) => window.setTimeout(resolve, MIN_RESPONSE_TRANSITION_MS)),
    ])
      .then(([result]) => {
        sessionIdRef.current = result.sessionId;
        sessionStateRef.current = result.sessionState;
        setFilters(result.filters);
        setFilteredProducts(result.products);
        setTotalResults(result.total);
        setHasMoreResults(result.products.length < result.total);
        pageRef.current = 1;
        const assistantReply = result.reply?.trim()
          || "I’ve updated your search. Tell me another detail if you’d like me to narrow it further.";
        setMessages((prev) => [
          ...prev,
          {
            id: nextMessageId('assistant'),
            sender: 'assistant',
            text: assistantReply,
            timestamp: nowStr(),
          },
        ]);
      })
      .catch((error) => {
        console.error('Chat message failed:', error);
        setMessages((prev) => [
          ...prev,
          {
            id: nextMessageId('error'),
            sender: 'assistant',
            text: "Sorry, I'm having trouble reaching the catalog right now — please try again in a moment.",
            timestamp: nowStr(),
          },
        ]);
      })
      .finally(() => {
        requestInFlightRef.current = false;
        setIsChatLoading(false);
        setIsProductsLoading(false);
      });
  }, [department]);

  const loadMore = useCallback(() => {
    if (isLoadingMore || isProductsLoading || !sessionStateRef.current || !hasMoreResults) return;
    setIsLoadingMore(true);
    const nextPage = pageRef.current + 1;

    searchProducts({
      ...buildPaginationQuery(sessionStateRef.current),
      page: nextPage,
      pageSize: 40,
    })
      .then((result) => {
        pageRef.current = nextPage;
        setFilteredProducts((prev) => [...prev, ...result.items.filter((item) => !prev.some((p) => p.id === item.id))]);
        setTotalResults(result.total);
        setHasMoreResults(result.hasMore);
      })
      .catch((error) => {
        console.error('Failed to load more results:', error);
      })
      .finally(() => {
        setIsLoadingMore(false);
      });
  }, [hasMoreResults, isLoadingMore, isProductsLoading]);

  const resetSession = useCallback(() => {
    const welcomeMessage: Message = {
      id: 'welcome',
      sender: 'assistant',
      text: `Assalam-o-Alaikum ${userName}. I am Dhaaga's AI Assistant. Tell me what celebratory moment you are dressing for, your preferred fabric, or a specific price range.`,
      timestamp: nowStr(),
    };

    if (!sessionIdRef.current) {
      // Nothing has been sent to the backend yet — just reset local UI state.
      setMessages([welcomeMessage]);
      setFilteredProducts([]);
      setTotalResults(0);
      setFilters(DEFAULT_FILTERS);
      sessionStateRef.current = null;
      setHasMoreResults(false);
      pageRef.current = 1;
      return;
    }

    setIsChatLoading(true);
    resetSessionApi(sessionIdRef.current)
      .then((result) => {
        sessionStateRef.current = result.sessionState;
        setFilters(result.filters);
        setFilteredProducts(result.products);
        setTotalResults(result.total);
        setHasMoreResults(false);
        pageRef.current = 1;
        setMessages([{ ...welcomeMessage, text: result.reply }]);
      })
      .catch((error) => {
        console.error('Failed to reset session:', error);
      })
      .finally(() => {
        setIsChatLoading(false);
      });
  }, [userName]);

  useEffect(() => {
    // Guards against React StrictMode double-invoking this effect in dev,
    // which would otherwise submit the initial query twice.
    if (hasTriggeredInitialRef.current) return;
    hasTriggeredInitialRef.current = true;

    const initial = composeInitialQuery(initialQuery, initialFilters);
    if (initial) {
      sendMessage(initial);
    } else if (initialSnapshotRef.current) {
      return;
    } else {
      setMessages([
        {
          id: 'welcome',
          sender: 'assistant',
          text: `Assalam-o-Alaikum ${userName}. I am Dhaaga's AI Assistant. Tell me what celebratory moment you are dressing for, your preferred fabric, or a specific price range.`,
          timestamp: nowStr(),
        },
      ]);
    }
    // Only run once on mount — this mirrors the initial-trigger effect the
    // component previously had.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const snapshot: ChatSnapshot = {
      entryQuery,
      sessionId: sessionIdRef.current,
      messages,
      products: filteredProducts,
      totalResults,
      filters,
      sessionState: sessionStateRef.current,
    };
    try {
      localStorage.setItem(CHAT_SNAPSHOT_KEY, JSON.stringify(snapshot));
      sessionStorage.removeItem(CHAT_SNAPSHOT_KEY);
    } catch (error) {
      try {
        localStorage.setItem(
          CHAT_SNAPSHOT_KEY,
          JSON.stringify({ ...snapshot, products: snapshot.products.slice(0, 40) })
        );
      } catch {
        console.warn('Could not persist the current chat snapshot:', error);
      }
    }
  }, [entryQuery, messages, filteredProducts, totalResults, filters]);

  return {
    messages,
    filteredProducts,
    totalResults,
    filters,
    isChatLoading,
    isProductsLoading,
    isLoadingMore,
    hasMoreResults,
    sendMessage,
    loadMore,
    resetSession,
  };
}
