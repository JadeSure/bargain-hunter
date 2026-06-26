'use server'

import { cookies } from 'next/headers'
import { redirect } from 'next/navigation'
import { logout } from '@/lib/api'

export async function logoutAction() {
  const cookieStore = await cookies()
  const session = cookieStore.get('session')?.value
  await logout(session ? `session=${session}` : undefined)
  cookieStore.delete('session')
  redirect('/')
}
