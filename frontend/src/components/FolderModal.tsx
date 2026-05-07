import { useState, useEffect, FormEvent } from 'react'
import { X, Loader2 } from 'lucide-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { createFolder, updateFolder, Folder } from '../api/folders'

interface Props {
  folder?: Folder | null
  onClose: () => void
}

export default function FolderModal({ folder, onClose }: Props) {
  const [name, setName] = useState(folder?.name ?? '')
  const [description, setDescription] = useState(folder?.description ?? '')
  const qc = useQueryClient()

  useEffect(() => {
    setName(folder?.name ?? '')
    setDescription(folder?.description ?? '')
  }, [folder])

  const mutation = useMutation({
    mutationFn: () =>
      folder
        ? updateFolder(folder._id, { name, description })
        : createFolder({ name, description }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['folders'] })
      onClose()
    },
  })

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    mutation.mutate()
  }

  return (
    <div className="fixed inset-0 bg-black/40 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <h2 className="font-semibold text-gray-900">
            {folder ? 'Edit Folder' : 'New Folder'}
          </h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {mutation.error && (
            <div className="bg-red-50 text-red-700 text-sm rounded-lg px-4 py-3 border border-red-100">
              {mutation.error instanceof Error ? mutation.error.message : 'Error'}
            </div>
          )}

          <div className="space-y-1">
            <label className="block text-sm font-medium text-gray-700">Name</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              placeholder="e.g. Research Papers"
              className="w-full border border-gray-200 rounded-xl px-4 py-2.5 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100 transition"
            />
          </div>

          <div className="space-y-1">
            <label className="block text-sm font-medium text-gray-700">
              Description <span className="text-gray-400 font-normal">(optional)</span>
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="What's in this folder?"
              rows={3}
              className="w-full border border-gray-200 rounded-xl px-4 py-2.5 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100 transition resize-none"
            />
          </div>

          <div className="flex gap-3 pt-1">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 border border-gray-200 text-gray-700 font-medium py-2.5 rounded-xl hover:bg-gray-50 transition text-sm"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={mutation.isPending || !name.trim()}
              className="flex-1 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400 text-white font-medium py-2.5 rounded-xl transition text-sm flex items-center justify-center gap-2"
            >
              {mutation.isPending && <Loader2 className="w-4 h-4 animate-spin" />}
              {folder ? 'Save Changes' : 'Create Folder'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
