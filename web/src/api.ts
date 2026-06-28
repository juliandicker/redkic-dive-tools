import type { TrimixBlendResponse, DivePlannerResponse } from './types'

const LOCAL = 'http://localhost:7071'

function base(): string {
  const h = window.location.hostname
  if (h === 'localhost' || h === '127.0.0.1' || h === '') return LOCAL
  return import.meta.env.VITE_API_BASE_URL ?? LOCAL
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(base() + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || res.statusText)
  }
  return res.json() as Promise<T>
}

export function trimixBlend(payload: unknown) {
  return post<TrimixBlendResponse>('/api/TrimixBlend', payload)
}

export function divePlan(payload: unknown) {
  return post<DivePlannerResponse>('/api/DivePlanner', payload)
}
