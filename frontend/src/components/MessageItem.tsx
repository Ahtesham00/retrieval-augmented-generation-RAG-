import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { ChevronDown, ChevronUp, FileText, Timer } from 'lucide-react'
import { ChatMessage, Citation } from '../api/chat'
import clsx from 'clsx'

function formatLatency(ms: number): string {
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`
}

function CitationsPanel({ citations }: { citations: Citation[] }) {
  const [open, setOpen] = useState(false)
  if (!citations.length) return null

  return (
    <div className="mt-3 border border-gray-200 rounded-xl overflow-hidden">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between px-4 py-2.5 bg-gray-50 hover:bg-gray-100 transition-colors text-sm font-medium text-gray-700"
      >
        <span className="flex items-center gap-1.5">
          <FileText className="w-3.5 h-3.5 text-gray-500" />
          Sources ({citations.length})
        </span>
        {open ? (
          <ChevronUp className="w-4 h-4 text-gray-400" />
        ) : (
          <ChevronDown className="w-4 h-4 text-gray-400" />
        )}
      </button>

      {open && (
        <div className="divide-y divide-gray-100">
          {citations.map((c, i) => (
            <div key={i} className="px-4 py-3 bg-white">
              <p className="text-xs font-semibold text-blue-700 mb-1 flex items-center gap-1">
                <FileText className="w-3 h-3" />
                {c.file_name}
                {c.score != null && (
                  <span className="ml-auto text-gray-400 font-normal">
                    score: {(c.score * 100).toFixed(0)}%
                  </span>
                )}
              </p>
              <p className="text-xs text-gray-600 leading-relaxed line-clamp-3">
                {c.snippet.slice(0, 200)}
                {c.snippet.length > 200 ? '…' : ''}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

interface StreamingItemProps {
  content: string
  citations: Citation[]
  isStreaming: boolean
  error: string | null
  latencyMs: number | null
}

export function StreamingMessageItem({ content, citations, isStreaming, error, latencyMs }: StreamingItemProps) {
  return (
    <div className="flex gap-3 group">
      <div className="w-8 h-8 rounded-full bg-gradient-to-br from-indigo-500 to-blue-600 flex items-center justify-center text-white text-xs font-bold flex-shrink-0 mt-0.5 shadow-sm">
        AI
      </div>
      <div className="flex-1 max-w-[85%]">
        <div className="bg-white border border-gray-200 rounded-2xl rounded-tl-sm px-5 py-4 shadow-sm">
          {error ? (
            <p className="text-red-500 text-sm">{error}</p>
          ) : (
            <div className="prose prose-sm max-w-none text-gray-800">
              <ReactMarkdown>{content}</ReactMarkdown>
              {isStreaming && <span className="cursor-blink" />}
            </div>
          )}
        </div>
        {!isStreaming && latencyMs != null && (
          <p className="flex items-center gap-1 text-[10px] text-gray-400 mt-1 opacity-0 group-hover:opacity-100 transition-opacity">
            <Timer className="w-3 h-3" />
            {formatLatency(latencyMs)}
          </p>
        )}
        {!isStreaming && citations.length > 0 && (
          <CitationsPanel citations={citations} />
        )}
      </div>
    </div>
  )
}

interface Props {
  message: ChatMessage
}

export default function MessageItem({ message }: Props) {
  const isUser = message.role === 'user'

  if (isUser) {
    return (
      <div className="flex gap-3 justify-end group">
        <div className="max-w-[75%]">
          <div className="bg-blue-600 text-white rounded-2xl rounded-tr-sm px-5 py-3.5 shadow-sm">
            <p className="text-sm leading-relaxed whitespace-pre-wrap">{message.content}</p>
          </div>
          <p className="text-[10px] text-gray-400 mt-1 text-right opacity-0 group-hover:opacity-100 transition-opacity">
            {new Date(message.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
          </p>
        </div>
        <div className="w-8 h-8 rounded-full bg-blue-100 flex items-center justify-center text-blue-600 text-xs font-bold flex-shrink-0 mt-0.5">
          U
        </div>
      </div>
    )
  }

  return (
    <div className="flex gap-3 group">
      <div className="w-8 h-8 rounded-full bg-gradient-to-br from-indigo-500 to-blue-600 flex items-center justify-center text-white text-xs font-bold flex-shrink-0 mt-0.5 shadow-sm">
        AI
      </div>
      <div className="flex-1 max-w-[85%]">
        <div className="bg-white border border-gray-200 rounded-2xl rounded-tl-sm px-5 py-4 shadow-sm">
          <div className="prose prose-sm max-w-none text-gray-800">
            <ReactMarkdown>{message.content}</ReactMarkdown>
          </div>
        </div>
        <p className="flex items-center gap-2 text-[10px] text-gray-400 mt-1 opacity-0 group-hover:opacity-100 transition-opacity">
          {new Date(message.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
          {message.retrieval_trace?.latency_ms != null && (
            <span className="flex items-center gap-0.5">
              <Timer className="w-3 h-3" />
              {formatLatency(message.retrieval_trace.latency_ms)}
            </span>
          )}
        </p>
        {message.citations && message.citations.length > 0 && (
          <CitationsPanel citations={message.citations} />
        )}
      </div>
    </div>
  )
}
