interface SubscriptionBadgeProps {
  tier: 'free' | 'pro' | 'premium'
}

export default function SubscriptionBadge({ tier }: SubscriptionBadgeProps) {
  const styles = {
    free: 'bg-bg-elevated text-text-muted',
    pro: 'bg-accent/10 text-accent',
    premium: 'bg-accent/15 text-accent',
  }

  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-md text-[10px] font-medium uppercase tracking-wider ${styles[tier]}`}>
      {tier}
    </span>
  )
}
