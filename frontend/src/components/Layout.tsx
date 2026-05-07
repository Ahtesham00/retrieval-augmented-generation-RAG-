import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { MessageSquare, LogOut, ChevronDown, FolderOpen } from 'lucide-react'
import { useAuthStore } from '../store/useAuthStore'
import { getFolders } from '../api/folders'
import Sidebar from './Sidebar'
import FileManager from './FileManager'
import ChatWindow from './ChatWindow'
import clsx from 'clsx'

export default function Layout() {
  const [selectedFolderId, setSelectedFolderId] = useState<string | null>(null)
  const [selectedConversationId, setSelectedConversationId] = useState<string | null>(null)
  const [showChat, setShowChat] = useState(false)

  const logout = useAuthStore((s) => s.logout)
  const userEmail = useAuthStore((s) => s.userEmail)

  const { data: folders = [] } = useQuery({
    queryKey: ['folders'],
    queryFn: getFolders,
    staleTime: 30_000,
  })

  const selectedFolder = folders.find((f) => f._id === selectedFolderId)

  function handleSelectFolder(id: string) {
    if (id !== selectedFolderId) {
      setSelectedFolderId(id)
      setSelectedConversationId(null)
      setShowChat(false)
    }
  }

  function handleSelectConversation(id: string | null) {
    setSelectedConversationId(id)
    if (id) setShowChat(true)
  }

  function handleNewChat() {
    setSelectedConversationId(null)
    setShowChat(true)
  }

  function handleConversationCreated(id: string) {
    setSelectedConversationId(id)
    setShowChat(true)
  }

  return (
    <div className="flex flex-col h-screen bg-gray-50">
      {/* Top bar */}
      <header className="h-14 bg-white border-b border-gray-100 flex items-center px-4 gap-4 flex-shrink-0 shadow-sm z-10">
        {/* Logo */}
        <div className="flex items-center gap-2.5 font-bold text-gray-900">
          <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center shadow-sm">
            <MessageSquare className="w-4 h-4 text-white" />
          </div>
          <span className="text-base">RAG Chat</span>
        </div>

        {/* Folder breadcrumb */}
        {selectedFolder && (
          <div className="flex items-center gap-1.5 ml-2 px-3 py-1.5 bg-gray-50 border border-gray-200 rounded-lg text-sm text-gray-700">
            <FolderOpen className="w-3.5 h-3.5 text-blue-500" />
            <span className="font-medium">{selectedFolder.name}</span>
            {selectedFolder.file_count > 0 && (
              <span className="text-gray-400 text-xs">· {selectedFolder.file_count} files</span>
            )}
          </div>
        )}

        <div className="ml-auto flex items-center gap-3">
          {/* View toggle when folder selected */}
          {selectedFolderId && (
            <div className="flex items-center gap-1 bg-gray-100 rounded-lg p-1">
              <button
                onClick={() => setShowChat(false)}
                className={clsx(
                  'px-3 py-1.5 rounded-md text-xs font-medium transition-all',
                  !showChat
                    ? 'bg-white text-gray-900 shadow-sm'
                    : 'text-gray-500 hover:text-gray-700',
                )}
              >
                Files
              </button>
              <button
                onClick={() => setShowChat(true)}
                className={clsx(
                  'px-3 py-1.5 rounded-md text-xs font-medium transition-all',
                  showChat
                    ? 'bg-white text-gray-900 shadow-sm'
                    : 'text-gray-500 hover:text-gray-700',
                )}
              >
                Chat
              </button>
            </div>
          )}

          {/* User */}
          {userEmail && (
            <span className="text-xs text-gray-500 hidden sm:block">{userEmail}</span>
          )}

          {/* Logout */}
          <button
            onClick={logout}
            className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-red-600 transition-colors px-2 py-1.5 rounded-lg hover:bg-red-50"
            title="Logout"
          >
            <LogOut className="w-4 h-4" />
            <span className="hidden sm:inline text-xs font-medium">Logout</span>
          </button>
        </div>
      </header>

      {/* Body */}
      <div className="flex flex-1 overflow-hidden">
        <Sidebar
          selectedFolderId={selectedFolderId}
          selectedConversationId={selectedConversationId}
          onSelectFolder={handleSelectFolder}
          onSelectConversation={handleSelectConversation}
          onNewChat={handleNewChat}
        />

        {/* Main panel */}
        <main className="flex-1 overflow-hidden">
          {!selectedFolderId ? (
            <div className="flex flex-col items-center justify-center h-full text-center p-8">
              <div className="w-16 h-16 bg-blue-50 rounded-2xl flex items-center justify-center mb-4">
                <FolderOpen className="w-8 h-8 text-blue-400" />
              </div>
              <h2 className="text-xl font-semibold text-gray-800 mb-2">Select a folder to start</h2>
              <p className="text-sm text-gray-500 max-w-sm">
                Create a folder, upload your documents, and start chatting with your knowledge base.
              </p>
            </div>
          ) : showChat ? (
            <ChatWindow
              key={selectedConversationId ?? 'new'}
              folderId={selectedFolderId}
              conversationId={selectedConversationId}
              onConversationCreated={handleConversationCreated}
            />
          ) : (
            <FileManager
              folderId={selectedFolderId}
              onStartChat={handleNewChat}
            />
          )}
        </main>
      </div>
    </div>
  )
}
