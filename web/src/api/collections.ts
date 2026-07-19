import { api } from './client';
import { ApiCollection } from '../types';

export async function fetchCollections(): Promise<ApiCollection[]> {
  return api.get<ApiCollection[]>('/collections');
}
