import { apiJson } from './client'

export interface Conversation {
  _id: string
  folder_id: string
  title: string
  created_at: string
  updated_at: string
}

export interface CreateConversationInput {
  folder_id: string
  title?: string
}

export function getConversations(folderId: string): Promise<Conversation[]> {
  return apiJson<Conversation[]>(`/folders/${folderId}/conversations`)
}

export function createConversation(data: CreateConversationInput): Promise<Conversation> {
  return apiJson<Conversation>(`/folders/${data.folder_id}/conversations`, {
    method: 'POST',
    body: JSON.stringify({ title: data.title }),
  })
}

export function deleteConversation(id: string): Promise<void> {
  return apiJson<void>(`/conversations/${id}`, { method: 'DELETE' })
}
