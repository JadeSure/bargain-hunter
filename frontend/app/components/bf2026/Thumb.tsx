const CATEGORY_EMOJI: Record<string, string> = {
  数码电子: '📱',
  家电厨房: '🍳',
  美妆个护: '💄',
  户外运动: '🏃',
  保健食品: '💊',
  礼品: '🎁',
  其他: '🛍️',
}

// Product thumbnail from OzBargain, hotlinked. The hidden page URL must never reach that host, hence no-referrer.
export default function Thumb({ image, name, category, size }: { image?: string; name: string; category: string; size: number }) {
  if (!image) {
    return (
      <span
        aria-hidden
        className="flex shrink-0 items-center justify-center rounded-lg bg-zinc-800"
        style={{ width: size, height: size, fontSize: size * 0.5 }}
      >
        {CATEGORY_EMOJI[category] ?? CATEGORY_EMOJI['其他']}
      </span>
    )
  }
  return (
    // Plain <img>: Next <Image> remote optimisation is not available on next-on-pages.
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={image}
      alt={name}
      width={size}
      height={size}
      referrerPolicy="no-referrer"
      loading="lazy"
      decoding="async"
      className="bf-img"
    />
  )
}
