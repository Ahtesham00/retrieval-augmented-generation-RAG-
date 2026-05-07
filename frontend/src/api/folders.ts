import { apiJson } from './client'

export interface Folder {
  _id: string
  name: string
  description?: string
  pinecone_namespace: string
  file_count: number
  chunk_count: number
  created_at: string
}

export interface CreateFolderInput {
  name: string
  description?: string
}

export interface UpdateFolderInput {
  name?: string
  description?: string
}

export function getFolders(): Promise<Folder[]> {
  return apiJson<Folder[]>('/folders')
}

export function createFolder(data: CreateFolderInput): Promise<Folder> {
  return apiJson<Folder>('/folders', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export function updateFolder(id: string, data: UpdateFolderInput): Promise<Folder> {
  return apiJson<Folder>(`/folders/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export function deleteFolder(id: string): Promise<void> {
  return apiJson<void>(`/folders/${id}`, { method: 'DELETE' })
}
