import { api } from './client';
import { toProducts } from './products';
import { ChatTurnResponse, Product, SessionState } from '../types';

export interface SessionMessageResult {
  sessionId: string;
  reply: string;
  sessionState: SessionState;
  filters: { category?: string; style: string; styles?: string[]; occasion: string; budget: string; color?: string; size?: string; age?: string };
  products: Product[];
  total: number;
  turnType: 'fast_path' | 'llm_extraction';
}

const DEFAULT_FILTERS: SessionMessageResult['filters'] = {
  style: 'All Styles',
  occasion: 'All Occasions',
  budget: 'All Budgets',
};

function describeBudget(budgetMax: number | null | undefined): string {
  return budgetMax ? `Under Rs. ${budgetMax.toLocaleString('en-PK')}` : 'All Budgets';
}

function normalizeFilters(response: ChatTurnResponse): SessionMessageResult['filters'] {
  const serverFilters = response.filters ?? {};
  const state = response.session_state;
  const styles = state.style_descriptors ?? [];
  return {
    category: serverFilters.category ?? state.category ?? undefined,
    style: serverFilters.style ?? (styles[0] ?? DEFAULT_FILTERS.style),
    styles: serverFilters.styles ?? (styles.length ? styles : undefined),
    occasion: serverFilters.occasion ?? state.occasion ?? DEFAULT_FILTERS.occasion,
    budget: serverFilters.budget ?? describeBudget(state.budget_max),
    color: serverFilters.color ?? state.color_preference ?? undefined,
    size: serverFilters.size ?? state.size ?? undefined,
    age: serverFilters.age ?? (
      state.child_age_months !== null && state.child_age_months !== undefined
        ? `${Math.floor(state.child_age_months / 12)} years`
        : undefined
    ),
  };
}

async function toResult(response: ChatTurnResponse): Promise<SessionMessageResult> {
  return {
    sessionId: response.session_id,
    reply: response.reply,
    sessionState: response.session_state,
    filters: normalizeFilters(response),
    products: await toProducts(response.products.items),
    total: response.products.total,
    turnType: response.turn_type,
  };
}

export async function sendSessionMessage(
  sessionId: string | null,
  query: string,
  department?: 'men' | 'women',
  sessionState?: SessionState | null
): Promise<SessionMessageResult> {
  const response = await api.post<ChatTurnResponse>('/session/message', {
    session_id: sessionId,
    query,
    department: department ?? null,
    session_state: sessionState ?? null,
  });
  return toResult(response);
}

export async function resetSession(sessionId: string): Promise<SessionMessageResult> {
  const response = await api.post<ChatTurnResponse>('/session/reset', { session_id: sessionId });
  return toResult(response);
}
