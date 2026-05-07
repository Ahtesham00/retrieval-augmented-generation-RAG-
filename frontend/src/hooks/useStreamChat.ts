import { useState, useRef, useCallback } from 'react'
import { streamMessage, Citation } from '../api/chat'
import { createConversation } from '../api/conversations'

export interface StreamingMessage {
  content: string
  citations: Citation[]
  isStreaming: boolean
  error: string | null
  latencyMs: number | null
}

export function useStreamChat(folderId: string | null) {
  const [streaming, setStreaming] = useState<StreamingMessage | null>(null)
  const abortRef = useRef<boolean>(false)

  const sendMessage = useCallback(
    async (
      content: string,
      conversationId: string | null,
      onConversationCreated: (id: string) => void,
      numQueries: number = 1,
    ): Promise<{ conversationId: string; citations: Citation[] } | null> => {
      if (!folderId) return null

      abortRef.current = false

      let convId = conversationId
      if (!convId) {
        try {
          const conv = await createConversation({
            folder_id: folderId,
            title: content.slice(0, 60),
          })
          convId = conv._id
          onConversationCreated(convId)
        } catch (err) {
          setStreaming({
            content: '',
            citations: [],
            isStreaming: false,
            error: err instanceof Error ? err.message : 'Failed to create conversation',
          })
          return null
        }
      }

      const startMs = Date.now()
      setStreaming({ content: '', citations: [], isStreaming: true, error: null, latencyMs: null })

      let accContent = ''
      let accCitations: Citation[] = []

      try {
        for await (const event of streamMessage(convId, content, numQueries)) {
          if (abortRef.current) break

          if (event.type === 'token') {
            accContent += event.content
            setStreaming({
              content: accContent,
              citations: accCitations,
              isStreaming: true,
              error: null,
              latencyMs: null,
            })
          } else if (event.type === 'citations') {
            accCitations = event.data
            setStreaming({
              content: accContent,
              citations: accCitations,
              isStreaming: true,
              error: null,
              latencyMs: null,
            })
          } else if (event.type === 'error') {
            setStreaming({
              content: accContent,
              citations: accCitations,
              isStreaming: false,
              error: event.content,
              latencyMs: Date.now() - startMs,
            })
            return null
          } else if (event.type === 'done') {
            break
          }
        }
      } catch (err) {
        setStreaming({
          content: accContent,
          citations: accCitations,
          isStreaming: false,
          error: err instanceof Error ? err.message : 'Stream error',
          latencyMs: Date.now() - startMs,
        })
        return null
      }

      setStreaming((prev) =>
        prev ? { ...prev, isStreaming: false, latencyMs: Date.now() - startMs } : null,
      )

      return { conversationId: convId, citations: accCitations }
    },
    [folderId],
  )

  const clearStreaming = useCallback(() => {
    abortRef.current = true
    setStreaming(null)
  }, [])

  return { streaming, sendMessage, clearStreaming }
}
