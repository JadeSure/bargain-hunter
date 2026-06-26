'use client'

import { createContext, useContext, useState, ReactNode } from 'react'
import type { SubscriberData, SubscriberUpdate } from '@/lib/api'
import { updateMe } from '@/lib/api'

interface UserContextValue {
  user: SubscriberData
  setUser: (u: SubscriberData) => void
  saveUpdate: (update: SubscriberUpdate) => Promise<void>
}

const UserContext = createContext<UserContextValue | null>(null)

export function useUser(): UserContextValue {
  const ctx = useContext(UserContext)
  if (!ctx) throw new Error('useUser must be used within UserProvider')
  return ctx
}

export function UserProvider({ initial, children }: { initial: SubscriberData; children: ReactNode }) {
  const [user, setUser] = useState<SubscriberData>(initial)

  async function saveUpdate(update: SubscriberUpdate) {
    await updateMe(update)
    setUser({ ...user, ...update })
  }

  return (
    <UserContext.Provider value={{ user, setUser, saveUpdate }}>
      {children}
    </UserContext.Provider>
  )
}
