import { useState, KeyboardEvent, useRef, useEffect } from 'react'
import { Send, Loader2, Zap, Search } from 'lucide-react'
import clsx from 'clsx'

const QUERY_OPTIONS = [
  { value: 1, label: '1×', description: 'Fast — single query, no expansion' },
  { value: 2, label: '2×', description: 'Balanced — 1 extra query variant' },
  { value: 4, label: '4×', description: 'Thorough — 3 extra query variants' },
]

interface Props {
  onSend: (content: string, numQueries: number) => void
  disabled?: boolean
  placeholder?: string
  numQueries: number
  onNumQueriesChange: (n: number) => void
}

export default function ChatInput({ onSend, disabled, placeholder, numQueries, onNumQueriesChange }: Props) {
  const [value, setValue] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
      textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 180) + 'px'
    }
  }, [value])

  function handleSend() {
    const trimmed = value.trim()
    if (!trimmed || disabled) return
    onSend(trimmed, numQueries)
    setValue('')
    if (textareaRef.current) textareaRef.current.style.height = 'auto'
  }

  function handleKey(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const selected = QUERY_OPTIONS.find((o) => o.value === numQueries) ?? QUERY_OPTIONS[0]

  return (
    <div className="border-t border-gray-100 bg-white px-4 py-4">
      <div className="max-w-4xl mx-auto space-y-2">
        {/* Query expansion selector */}
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1.5 text-[11px] text-gray-400">
            <Search className="w-3 h-3" />
            <span>Query expansion</span>
          </div>
          <div className="flex items-center gap-1">
            {QUERY_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                onClick={() => onNumQueriesChange(opt.value)}
                disabled={disabled}
                title={opt.description}
                className={clsx(
                  'px-2.5 py-0.5 rounded-md text-[11px] font-medium transition-all',
                  numQueries === opt.value
                    ? 'bg-blue-100 text-blue-700 border border-blue-200'
                    : 'text-gray-400 hover:text-gray-600 hover:bg-gray-100 border border-transparent',
                )}
              >
                {opt.label}
              </button>
            ))}
          </div>
          {numQueries > 1 && (
            <span className="text-[10px] text-amber-500 flex items-center gap-1">
              <Zap className="w-3 h-3" />
              +{(numQueries - 1) * 3}–{(numQueries - 1) * 10}s latency
            </span>
          )}
        </div>

        {/* Input row */}
        <div className={clsx(
          'flex items-end gap-3 bg-gray-50 border rounded-2xl px-4 py-3 transition-all',
          disabled ? 'border-gray-100 opacity-70' : 'border-gray-200 focus-within:border-blue-400 focus-within:ring-2 focus-within:ring-blue-100 focus-within:bg-white',
        )}>
          <textarea
            ref={textareaRef}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={handleKey}
            disabled={disabled}
            placeholder={placeholder ?? 'Ask a question about your documents… (Enter to send, Shift+Enter for new line)'}
            rows={1}
            className="flex-1 bg-transparent outline-none resize-none text-sm text-gray-900 placeholder-gray-400 max-h-44 scrollbar-thin"
          />
          <button
            onClick={handleSend}
            disabled={!value.trim() || disabled}
            className={clsx(
              'flex-shrink-0 w-9 h-9 rounded-xl flex items-center justify-center transition-all',
              value.trim() && !disabled
                ? 'bg-blue-600 text-white hover:bg-blue-700 shadow-sm'
                : 'bg-gray-200 text-gray-400 cursor-not-allowed',
            )}
          >
            {disabled ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Send className="w-4 h-4" />
            )}
          </button>
        </div>
        <p className="text-[10px] text-gray-400 text-center">
          Responses are generated from your uploaded documents.
        </p>
      </div>
    </div>
  )
}
