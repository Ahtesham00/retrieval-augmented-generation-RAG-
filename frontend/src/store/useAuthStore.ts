import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface AuthState {
  token: string | null
  refreshToken: string | null
  userEmail: string | null
  setTokens: (token: string, refreshToken: string, email?: string) => void
  setEmail: (email: string) => void
  logout: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      refreshToken: null,
      userEmail: null,
      setTokens: (token, refreshToken, email) =>
        set((s) => ({
          token,
          refreshToken,
          userEmail: email ?? s.userEmail,
        })),
      setEmail: (email) => set({ userEmail: email }),
      logout: () => set({ token: null, refreshToken: null, userEmail: null }),
    }),
    {
      name: 'rag-auth',
      partialize: (s) => ({
        token: s.token,
        refreshToken: s.refreshToken,
        userEmail: s.userEmail,
      }),
    },
  ),
)
