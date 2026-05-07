import { useState, useRef, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  FolderOpen, FolderClosed, Plus, MessageSquare, Trash2,
  Pencil, ChevronRight, Loader2, Check, X
} from 'lucide-react'
import { getFolders, Folder } from '../api/folders'
import { getConversations, createConversation, deleteConversation } from '../api/conversations'
import FolderModal from './FolderModal'
import clsx from 'clsx'

interface Props {
  selectedFolderId: string | null
  selectedConversationId: string | null
  onSelectFolder: (id: string) => void
  onSelectConversation: (id: string | null) => void
  onNewChat: () => void
}

function ConversationList({
  folderId,
  selectedId,
  onSelect,
}: {
  folderId: string
  selectedId: string | null
  onSelect: (id: string | null) => void
}) {
  const qc = useQueryClient()
  const [isCreating, setIsCreating] = useState(false)
  const [newTitle, setNewTitle] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  const { data: convs = [], isLoading } = useQuery({
    queryKey: ['conversations', folderId],
    queryFn: () => getConversations(folderId),
    staleTime: 10_000,
  })

  const createMutation = useMutation({
    mutationFn: () => createConversation({ folder_id: folderId, title: newTitle.trim() || 'New conversation' }),
    onSuccess: (conv) => {
      qc.invalidateQueries({ queryKey: ['conversations', folderId] })
      setIsCreating(false)
      setNewTitle('')
      onSelect(conv._id)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: deleteConversation,
    onSuccess: (_, id) => {
      qc.invalidateQueries({ queryKey: ['conversations', folderId] })
      if (selectedId === id) onSelect(null)
    },
  })

  useEffect(() => {
    if (isCreating) inputRef.current?.focus()
  }, [isCreating])

  function startCreating() {
    setNewTitle('')
    setIsCreating(true)
  }

  function cancelCreating() {
    setIsCreating(false)
    setNewTitle('')
  }

  function submitCreate() {
    if (createMutation.isPending) return
    createMutation.mutate()
  }

  if (isLoading) {
    return (
      <div className="px-3 py-2 flex items-center gap-2 text-gray-400 text-xs">
        <Loader2 className="w-3 h-3 animate-spin" />
        Loading…
      </div>
    )
  }

  return (
    <div className="space-y-0.5">
      {/* Inline header row with + button */}
      <div className="flex items-center justify-between px-1 mb-1">
        <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider py-1">
          Conversations
        </p>
        <button
          onClick={startCreating}
          className="text-gray-400 hover:text-blue-600 transition-colors"
          title="New conversation"
        >
          <Plus className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Inline new-conversation input */}
      {isCreating && (
        <div className="flex items-center gap-1 px-2 py-1.5 mb-1 bg-blue-50 rounded-lg border border-blue-100">
          <MessageSquare className="w-3 h-3 text-blue-400 flex-shrink-0" />
          <input
            ref={inputRef}
            value={newTitle}
            onChange={(e) => setNewTitle(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') submitCreate()
              if (e.key === 'Escape') cancelCreating()
            }}
            placeholder="Conversation name…"
            className="flex-1 text-xs bg-transparent outline-none text-gray-700 placeholder-gray-400 min-w-0"
          />
          <button
            onClick={submitCreate}
            disabled={createMutation.isPending}
            className="text-blue-500 hover:text-blue-700 disabled:opacity-50 flex-shrink-0"
            title="Create"
          >
            {createMutation.isPending
              ? <Loader2 className="w-3 h-3 animate-spin" />
              : <Check className="w-3 h-3" />}
          </button>
          <button onClick={cancelCreating} className="text-gray-400 hover:text-gray-600 flex-shrink-0" title="Cancel">
            <X className="w-3 h-3" />
          </button>
        </div>
      )}

      {convs.length === 0 && !isCreating && (
        <p className="px-3 py-2 text-xs text-gray-400">No conversations yet</p>
      )}
      {convs.map((conv) => (
        <div
          key={conv._id}
          className={clsx(
            'group flex items-center gap-2 px-3 py-2 rounded-lg cursor-pointer transition-colors',
            selectedId === conv._id
              ? 'bg-blue-50 text-blue-700'
              : 'text-gray-600 hover:bg-gray-100',
          )}
          onClick={() => onSelect(conv._id)}
        >
          <MessageSquare className="w-3.5 h-3.5 flex-shrink-0 opacity-60" />
          <span className="flex-1 text-xs truncate font-medium">{conv.title || 'Untitled'}</span>
          <button
            onClick={(e) => {
              e.stopPropagation()
              if (confirm('Delete this conversation?')) deleteMutation.mutate(conv._id)
            }}
            className="opacity-0 group-hover:opacity-100 text-gray-400 hover:text-red-500 transition-all flex-shrink-0"
          >
            <Trash2 className="w-3 h-3" />
          </button>
        </div>
      ))}
    </div>
  )
}

export default function Sidebar({
  selectedFolderId,
  selectedConversationId,
  onSelectFolder,
  onSelectConversation,
  onNewChat,
}: Props) {
  const [modalOpen, setModalOpen] = useState(false)
  const [editingFolder, setEditingFolder] = useState<Folder | null>(null)

  const { data: folders = [], isLoading } = useQuery({
    queryKey: ['folders'],
    queryFn: getFolders,
    staleTime: 30_000,
  })

  function openCreate() {
    setEditingFolder(null)
    setModalOpen(true)
  }
  function openEdit(f: Folder, e: React.MouseEvent) {
    e.stopPropagation()
    setEditingFolder(f)
    setModalOpen(true)
  }

  return (
    <>
      <aside className="w-[280px] flex-shrink-0 bg-white border-r border-gray-100 flex flex-col h-full overflow-hidden">
        {/* Header */}
        <div className="px-4 py-4 border-b border-gray-100">
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Folders</p>
        </div>

        {/* Folder list */}
        <div className="flex-1 overflow-y-auto scrollbar-thin py-2">
          {isLoading ? (
            <div className="px-4 py-3 flex items-center gap-2 text-gray-400 text-sm">
              <Loader2 className="w-4 h-4 animate-spin" />
              Loading…
            </div>
          ) : folders.length === 0 ? (
            <p className="px-4 py-3 text-sm text-gray-400">No folders yet</p>
          ) : (
            <div className="space-y-0.5 px-2">
              {folders.map((folder) => {
                const isSelected = selectedFolderId === folder._id
                return (
                  <div key={folder._id}>
                    <div
                      onClick={() => onSelectFolder(folder._id)}
                      className={clsx(
                        'group flex items-center gap-2.5 px-3 py-2.5 rounded-xl cursor-pointer transition-colors',
                        isSelected
                          ? 'bg-blue-50 text-blue-700'
                          : 'text-gray-700 hover:bg-gray-50',
                      )}
                    >
                      {isSelected ? (
                        <FolderOpen className="w-4 h-4 flex-shrink-0 text-blue-500" />
                      ) : (
                        <FolderClosed className="w-4 h-4 flex-shrink-0 text-gray-400" />
                      )}
                      <span className="flex-1 text-sm font-medium truncate">{folder.name}</span>
                      {isSelected && (
                        <ChevronRight className="w-3.5 h-3.5 text-blue-400" />
                      )}
                      <button
                        onClick={(e) => openEdit(folder, e)}
                        className="opacity-0 group-hover:opacity-100 text-gray-400 hover:text-gray-600 transition-all flex-shrink-0"
                        title="Edit folder"
                      >
                        <Pencil className="w-3 h-3" />
                      </button>
                    </div>

                    {/* Conversations for selected folder */}
                    {isSelected && (
                      <div className="ml-3 mt-0.5 pl-3 border-l border-gray-100">
                        <ConversationList
                          folderId={folder._id}
                          selectedId={selectedConversationId}
                          onSelect={onSelectConversation}
                        />
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* New folder button */}
        <div className="p-3 border-t border-gray-100">
          <button
            onClick={openCreate}
            className="w-full flex items-center gap-2 px-3 py-2.5 rounded-xl text-sm text-gray-600 hover:bg-gray-50 hover:text-blue-600 transition-colors font-medium"
          >
            <Plus className="w-4 h-4" />
            New Folder
          </button>
        </div>
      </aside>

      {modalOpen && (
        <FolderModal
          folder={editingFolder}
          onClose={() => setModalOpen(false)}
        />
      )}
    </>
  )
}
