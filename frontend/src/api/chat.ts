import { apiJson } from './client'
import { useAuthStore } from '../store/useAuthStore'

const BASE_URL = 'http://localhost:8000'

export interface Citation {
  chunk_id: string
  file_name: string
  snippet: string
  score: number
}

export interface RetrievalTrace {
  latency_ms: number
  model: string
  retrieved_chunk_ids: string[]
  rerank_scores: number[]
}

export interface ChatMessage {
  _id: string
  role: 'user' | 'assistant'
  content: string
  citations?: Citation[]
  retrieval_trace?: RetrievalTrace | null
  created_at: string
}

export interface SSEToken {
  type: 'token'
  content: string
}

export interface SSECitations {
  type: 'citations'
  data: Citation[]
}

export interface SSEDone {
  type: 'done'
}

export interface SSEError {
  type: 'error'
  content: string
}

export type SSEEvent = SSEToken | SSECitations | SSEDone | SSEError

export function getMessages(conversationId: string): Promise<ChatMessage[]> {
  return apiJson<ChatMessage[]>(`/conversations/${conversationId}/messages`)
}

export async function* streamMessage(
  conversationId: string,
  content: string,
  numQueries: number = 1,
): AsyncGenerator<SSEEvent> {
  const token = useAuthStore.getState().token
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    Accept: 'text/event-stream',
  }
  if (token) headers['Authorization'] = `Bearer ${token}`

  const response = await fetch(
    `${BASE_URL}/conversations/${conversationId}/messages`,
    {
      method: 'POST',
      headers,
      body: JSON.stringify({ content, num_queries: numQueries }),
    },
  )

  if (!response.ok) {
    const text = await response.text().catch(() => response.statusText)
    throw new Error(text || `HTTP ${response.status}`)
  }

  const reader = response.body!.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })

    // Split on double newlines (SSE event boundaries)
    const parts = buffer.split('\n\n')
    buffer = parts.pop() ?? ''

    for (const part of parts) {
      for (const line of part.split('\n')) {
        if (line.startsWith('data: ')) {
          const raw = line.slice(6).trim()
          if (!raw) continue
          try {
            const event = JSON.parse(raw) as SSEEvent
            yield event
          } catch {
            // ignore malformed lines
          }
        }
      }
    }
  }

  // Flush remaining buffer
  if (buffer) {
    for (const line of buffer.split('\n')) {
      if (line.startsWith('data: ')) {
        const raw = line.slice(6).trim()
        if (!raw) continue
        try {
          const event = JSON.parse(raw) as SSEEvent
          yield event
        } catch {
          // ignore
        }
      }
    }
  }
}
