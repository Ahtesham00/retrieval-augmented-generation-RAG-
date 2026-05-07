import { apiJson, apiFetch } from './client'

export type FileStatus = 'processing' | 'embedding' | 'ready' | 'failed'

export interface FolderFile {
  _id: string
  folder_id: string
  file_name: string
  file_extension: string
  content_type: string
  status: FileStatus
  chunk_count: number
  parsing_strategy?: string
  size_bytes: number
  error?: string
  created_at: string
}

export function getFiles(folderId: string): Promise<FolderFile[]> {
  return apiJson<FolderFile[]>(`/folders/${folderId}/files`)
}

export async function uploadFiles(folderId: string, files: File[]): Promise<FolderFile[]> {
  const formData = new FormData()
  for (const file of files) {
    formData.append('files', file)
  }
  const res = await apiFetch(`/folders/${folderId}/files`, {
    method: 'POST',
    body: formData,
  })
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText)
    throw new Error(text || `Upload failed: HTTP ${res.status}`)
  }
  return res.json()
}

export function deleteFile(fileId: string): Promise<void> {
  return apiJson<void>(`/files/${fileId}`, { method: 'DELETE' })
}
