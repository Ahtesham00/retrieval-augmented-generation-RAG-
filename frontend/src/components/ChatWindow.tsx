import { useEffect, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { MessageSquare, Sparkles } from 'lucide-react'
import { getMessages } from '../api/chat'
import { useStreamChat } from '../hooks/useStreamChat'
import MessageItem, { StreamingMessageItem } from './MessageItem'
import ChatInput from './ChatInput'

interface Props {
  folderId: string
  conversationId: string | null
  onConversationCreated: (id: string) => void
}

const SUGGESTIONS = [
  'Summarize the key points from my documents',
  'What are the main topics covered?',
  'Find any action items or deadlines mentioned',
  'Explain the most important concepts',
]

export default function ChatWindow({ folderId, conversationId, onConversationCreated }: Props) {
  const qc = useQueryClient()
  const bottomRef = useRef<HTMLDivElement>(null)
  const [numQueries, setNumQueries] = useState(1)
  const { streaming, sendMessage, clearStreaming } = useStreamChat(folderId)

  const { data: messages = [], isLoading } = useQuery({
    queryKey: ['messages', conversationId],
    queryFn: () => getMessages(conversationId!),
    enabled: !!conversationId,
    staleTime: 30_000,
  })

  // Scroll to bottom on new content
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages.length, streaming?.content])

  // Clear streaming state when switching conversations
  useEffect(() => {
    clearStreaming()
  }, [conversationId, clearStreaming])

  async function handleSend(content: string, nq: number = numQueries) {
    // Optimistically add user message to UI
    const tempUserMsg = {
      _id: `tmp-${Date.now()}`,
      role: 'user' as const,
      content,
      created_at: new Date().toISOString(),
    }

    if (conversationId) {
      qc.setQueryData(['messages', conversationId], (old: typeof messages) => [
        ...(old ?? []),
        tempUserMsg,
      ])
    }

    const result = await sendMessage(content, conversationId, (newId) => {
      onConversationCreated(newId)
      qc.setQueryData(['messages', newId], [tempUserMsg])
    }, nq)

    if (result) {
      // Clear streaming state BEFORE refetching so the StreamingMessageItem
      // disappears at the same moment the real persisted messages arrive,
      // preventing the duplicate-response flash.
      clearStreaming()
      await qc.invalidateQueries({ queryKey: ['messages', result.conversationId] })
      await qc.invalidateQueries({ queryKey: ['conversations', folderId] })
    }
  }

  const isStreaming = !!streaming?.isStreaming
  const isEmpty = !isLoading && messages.length === 0 && !streaming

  return (
    <div className="flex flex-col h-full">
      {/* Messages area */}
      <div className="flex-1 overflow-y-auto scrollbar-thin px-4 py-6">
        <div className="max-w-4xl mx-auto space-y-6">
          {isEmpty && (
            <div className="flex flex-col items-center justify-center py-16 text-center">
              <div className="w-16 h-16 bg-gradient-to-br from-blue-100 to-indigo-100 rounded-2xl flex items-center justify-center mb-4">
                <MessageSquare className="w-8 h-8 text-blue-500" />
              </div>
              <h3 className="text-lg font-semibold text-gray-800 mb-1">
                Ask anything about your documents
              </h3>
              <p className="text-sm text-gray-500 mb-8 max-w-sm">
                Your documents are ready. Start a conversation to get answers, summaries, and insights.
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 w-full max-w-xl">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    onClick={() => handleSend(s, numQueries)}
                    disabled={isStreaming}
                    className="flex items-center gap-2 text-left text-sm text-gray-700 bg-white border border-gray-200 hover:border-blue-300 hover:bg-blue-50 rounded-xl px-4 py-3 transition-all group"
                  >
                    <Sparkles className="w-3.5 h-3.5 text-blue-400 flex-shrink-0 group-hover:text-blue-500" />
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}

          {!conversationId && !isEmpty && null}

          {messages.map((msg) => (
            <MessageItem key={msg._id} message={msg} />
          ))}

          {streaming && (
            <StreamingMessageItem
              content={streaming.content}
              citations={streaming.citations}
              isStreaming={streaming.isStreaming}
              error={streaming.error}
              latencyMs={streaming.latencyMs}
            />
          )}

          <div ref={bottomRef} />
        </div>
      </div>

      {/* Input */}
      <ChatInput
        onSend={handleSend}
        disabled={isStreaming}
        placeholder={
          messages.length === 0 && !conversationId
            ? 'Ask your first question…'
            : 'Ask a follow-up question…'
        }
        numQueries={numQueries}
        onNumQueriesChange={setNumQueries}
      />
    </div>
  )
}
