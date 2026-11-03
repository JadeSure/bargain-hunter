// Presentational bits shared by the server page and the client explorer. No hooks and no
// server-only APIs, so both sides can import them.

export function Section({ id, emoji, title, children }: { id?: string; emoji: string; title: string; children: React.ReactNode }) {
  return (
    <section id={id} className="bf-section">
      <h2 className="mb-5 text-xl font-semibold text-zinc-50">
        <span aria-hidden className="mr-2">{emoji}</span>{title}
      </h2>
      {children}
    </section>
  )
}

export const Takeaway = ({ children }: { children: React.ReactNode }) => (
  <p className="mb-5 text-lg font-bold leading-snug text-zinc-50 sm:text-xl">{children}</p>
)
export const Evidence = ({ children }: { children: React.ReactNode }) => (
  <p className="mt-5 text-xs leading-relaxed text-zinc-400">{children}</p>
)
export const SubHead = ({ children }: { children: React.ReactNode }) => (
  <h3 className="mb-3 text-sm font-semibold text-zinc-300">{children}</h3>
)

export function Src({ href, children }: { href: string; children: React.ReactNode }) {
  if (!href.startsWith('http') && !(href.startsWith('/') && !href.startsWith('//'))) return <>{children}</>
  const external = href.startsWith('http')
  return (
    <a href={href} {...(external ? { target: '_blank', rel: 'noopener noreferrer' } : {})} className="bf-link">
      {children}
    </a>
  )
}
