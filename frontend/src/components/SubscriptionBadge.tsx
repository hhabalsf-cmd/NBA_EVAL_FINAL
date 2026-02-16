interface SubscriptionBadgeProps {
  tier: 'free' | 'pro' | 'premium'
}

export default function SubscriptionBadge({ tier }: SubscriptionBadgeProps) {
  const styles = {
    free: 'bg-bg-elevated text-text-muted',
    pro: 'bg-accent/15 text-accent',
    premium: 'bg-accent-gold/15 text-accent-gold',
  }

  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wider ${styles[tier]}`}>
      {tier}
    </span>
  )
}
