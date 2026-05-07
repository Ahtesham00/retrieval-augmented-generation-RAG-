import { useState, useRef, useEffect, useCallback, DragEvent } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Upload, FileText, Trash2, Loader2, AlertCircle,
  CheckCircle2, Clock, Zap, RefreshCw, MessageSquarePlus
} from 'lucide-react'
import { getFiles, uploadFiles, deleteFile, FolderFile, FileStatus } from '../api/files'
import { useAuthStore } from '../store/useAuthStore'
import clsx from 'clsx'

const BASE_URL = 'http://localhost:8000'

function StatusBadge({ status }: { status: FileStatus }) {
  const config = {
    processing: { label: 'Processing', color: 'bg-yellow-100 text-yellow-700 border-yellow-200', icon: Clock },
    embedding: { label: 'Embedding', color: 'bg-blue-100 text-blue-700 border-blue-200', icon: Zap },
    ready: { label: 'Ready', color: 'bg-green-100 text-green-700 border-green-200', icon: CheckCircle2 },
    failed: { label: 'Failed', color: 'bg-red-100 text-red-700 border-red-200', icon: AlertCircle },
  }
  const { label, color, icon: Icon } = config[status]
  return (
    <span className={clsx('inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full border', color)}>
      <Icon className="w-3 h-3" />
      {label}
    </span>
  )
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

interface Props {
  folderId: string
  onStartChat: () => void
}

export default function FileManager({ folderId, onStartChat }: Props) {
  const [isDragging, setIsDragging] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const qc = useQueryClient()
  const token = useAuthStore((s) => s.token)

  const { data: files = [], isLoading } = useQuery({
    queryKey: ['files', folderId],
    queryFn: () => getFiles(folderId),
    refetchInterval: (query) => {
      const data = query.state.data as FolderFile[] | undefined
      const hasActive = data?.some(
        (f) => f.status === 'processing' || f.status === 'embedding',
      )
      return hasActive ? 3000 : false
    },
  })

  // WebSocket for real-time status
  useEffect(() => {
    if (!token) return
    const ws = new WebSocket(
      `ws://localhost:8000/folders/${folderId}/files/status`,
    )
    wsRef.current = ws
    ws.onmessage = (e) => {
      try {
        const update = JSON.parse(e.data)
        qc.setQueryData<FolderFile[]>(['files', folderId], (old) =>
          old?.map((f) =>
            f._id === update.file_id
              ? { ...f, status: update.status, error: update.error, chunk_count: update.chunk_count }
              : f,
          ) ?? [],
        )
      } catch {
        // ignore
      }
    }
    ws.onerror = () => ws.close()
    return () => ws.close()
  }, [folderId, token, qc])

  const deleteMutation = useMutation({
    mutationFn: deleteFile,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['files', folderId] }),
  })

  const doUpload = useCallback(
    async (selectedFiles: File[]) => {
      if (!selectedFiles.length) return
      setUploading(true)
      setUploadError(null)
      try {
        await uploadFiles(folderId, selectedFiles)
        qc.invalidateQueries({ queryKey: ['files', folderId] })
      } catch (err) {
        setUploadError(err instanceof Error ? err.message : 'Upload failed')
      } finally {
        setUploading(false)
      }
    },
    [folderId, qc],
  )

  function onDragOver(e: DragEvent) {
    e.preventDefault()
    setIsDragging(true)
  }
  function onDragLeave() {
    setIsDragging(false)
  }
  function onDrop(e: DragEvent) {
    e.preventDefault()
    setIsDragging(false)
    doUpload(Array.from(e.dataTransfer.files))
  }
  function onFileInput() {
    const files = Array.from(fileInputRef.current?.files ?? [])
    doUpload(files)
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const readyCount = files.filter((f) => f.status === 'ready').length

  return (
    <div className="flex flex-col h-full p-6 gap-6 overflow-y-auto scrollbar-thin">
      {/* Upload zone */}
      <div
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onDrop={onDrop}
        onClick={() => !uploading && fileInputRef.current?.click()}
        className={clsx(
          'border-2 border-dashed rounded-2xl p-10 text-center cursor-pointer transition-all',
          isDragging
            ? 'border-blue-400 bg-blue-50'
            : 'border-gray-200 hover:border-blue-300 hover:bg-gray-50',
          uploading && 'pointer-events-none opacity-70',
        )}
      >
        <input
          ref={fileInputRef}
          type="file"
          multiple
          className="hidden"
          onChange={onFileInput}
        />
        {uploading ? (
          <div className="flex flex-col items-center gap-2 text-blue-600">
            <Loader2 className="w-8 h-8 animate-spin" />
            <p className="text-sm font-medium">Uploading files…</p>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-2">
            <div className="w-12 h-12 bg-blue-50 rounded-xl flex items-center justify-center">
              <Upload className="w-6 h-6 text-blue-500" />
            </div>
            <p className="text-sm font-medium text-gray-700">
              Drop files here or <span className="text-blue-600">click to browse</span>
            </p>
            <p className="text-xs text-gray-400">PDF, DOCX, TXT, MD and more</p>
          </div>
        )}
      </div>

      {uploadError && (
        <div className="bg-red-50 text-red-700 text-sm rounded-xl px-4 py-3 border border-red-100 flex items-center gap-2">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          {uploadError}
        </div>
      )}

      {/* File list */}
      {isLoading ? (
        <div className="flex items-center justify-center py-12 text-gray-400">
          <Loader2 className="w-6 h-6 animate-spin mr-2" />
          <span className="text-sm">Loading files…</span>
        </div>
      ) : files.length === 0 ? (
        <div className="text-center py-12 text-gray-400">
          <FileText className="w-10 h-10 mx-auto mb-2 opacity-30" />
          <p className="text-sm">No files yet. Upload some to get started.</p>
        </div>
      ) : (
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-gray-700">
              Files <span className="text-gray-400 font-normal">({files.length})</span>
            </h3>
            <button
              onClick={() => qc.invalidateQueries({ queryKey: ['files', folderId] })}
              className="text-gray-400 hover:text-gray-600 transition-colors"
              title="Refresh"
            >
              <RefreshCw className="w-4 h-4" />
            </button>
          </div>

          {files.map((file) => (
            <div
              key={file._id}
              className="flex items-center gap-3 bg-white border border-gray-100 rounded-xl px-4 py-3 hover:border-gray-200 transition-colors group"
            >
              <FileText className="w-5 h-5 text-gray-400 flex-shrink-0" />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-gray-800 truncate">{file.file_name}</p>
                <p className="text-xs text-gray-400">
                  {formatBytes(file.size_bytes)}
                  {file.chunk_count > 0 && ` · ${file.chunk_count} chunks`}
                  {file.error && (
                    <span className="text-red-500 ml-1" title={file.error}>· {file.error.slice(0, 40)}</span>
                  )}
                </p>
              </div>
              <StatusBadge status={file.status} />
              <button
                onClick={() => deleteMutation.mutate(file._id)}
                disabled={deleteMutation.isPending}
                className="opacity-0 group-hover:opacity-100 text-gray-400 hover:text-red-500 transition-all flex-shrink-0"
                title="Delete file"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Start chat CTA */}
      {readyCount > 0 && (
        <div className="mt-auto bg-gradient-to-r from-blue-50 to-indigo-50 border border-blue-100 rounded-2xl p-5 text-center">
          <p className="text-sm text-gray-600 mb-3">
            {readyCount} file{readyCount !== 1 ? 's' : ''} ready — start asking questions!
          </p>
          <button
            onClick={onStartChat}
            className="inline-flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold px-5 py-2.5 rounded-xl transition-colors shadow-sm"
          >
            <MessageSquarePlus className="w-4 h-4" />
            Start a Conversation
          </button>
        </div>
      )}
    </div>
  )
}
