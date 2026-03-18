import { X } from 'lucide-react'

interface TermsModalProps {
  isOpen: boolean
  onAccept: () => void
  onClose: () => void
  canDismiss?: boolean
}

export default function TermsModal({ isOpen, onAccept, onClose, canDismiss = true }: TermsModalProps) {
  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4">
      <div className="relative w-full max-w-2xl max-h-[80vh] flex flex-col bg-bg-secondary rounded-xl border border-border overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border">
          <h2 className="text-lg font-semibold text-text-primary">Terms of Service</h2>
          {canDismiss && (
            <button
              onClick={onClose}
              className="p-1 rounded-lg hover:bg-bg-tertiary text-text-muted transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          )}
        </div>

        {/* Scrollable Content */}
        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4 text-sm text-text-secondary leading-relaxed">
          <p className="text-xs text-text-muted">Last updated: March 12, 2026</p>

          <section>
            <h3 className="text-text-primary font-semibold mb-2">1. Acceptance of Terms</h3>
            <p>
              By creating an account and using this platform, you agree to be bound by these
              Terms of Service. If you do not agree, do not create an account or use the service.
            </p>
          </section>

          <section>
            <h3 className="text-text-primary font-semibold mb-2">2. Age Requirement</h3>
            <p>
              You must be at least 18 years of age to use this service. By creating an account,
              you represent and warrant that you are at least 18 years old.
            </p>
          </section>

          <section>
            <h3 className="text-text-primary font-semibold mb-2">3. Entertainment Purpose Only</h3>
            <p>
              All predictions, analyses, and statistical outputs provided by this platform are
              for <strong>entertainment and informational purposes only</strong>. They do not
              constitute financial advice, betting advice, or any form of professional guidance.
            </p>
          </section>

          <section>
            <h3 className="text-text-primary font-semibold mb-2">4. No Guaranteed Outcomes</h3>
            <p>
              Machine learning predictions are probabilistic in nature. Past performance does not
              guarantee future results. The platform makes no warranties regarding the accuracy,
              reliability, or completeness of any prediction or analysis.
            </p>
          </section>

          <section>
            <h3 className="text-text-primary font-semibold mb-2">5. Assumption of Risk</h3>
            <p>
              You acknowledge that any decisions made based on the information provided by this
              platform are made at your own risk. The platform, its operators, and affiliates are
              not responsible for any financial losses or damages resulting from the use of
              predictions or analyses.
            </p>
          </section>

          <section>
            <h3 className="text-text-primary font-semibold mb-2">6. User Accounts</h3>
            <p>
              You are responsible for maintaining the confidentiality of your account credentials.
              You agree to notify us immediately of any unauthorized use of your account.
            </p>
          </section>

          <section>
            <h3 className="text-text-primary font-semibold mb-2">7. Data Collection & Usage</h3>
            <p>
              We collect and store account information (email, username) and usage data (picks,
              predictions) to provide and improve the service. Your data will not be sold to
              third parties. Pick history and prediction data may be used in aggregate for
              platform analytics.
            </p>
          </section>

          <section>
            <h3 className="text-text-primary font-semibold mb-2">8. Prohibited Conduct</h3>
            <p>You agree not to:</p>
            <ul className="list-disc list-inside mt-1 space-y-1 text-text-muted">
              <li>Use the platform for any unlawful purpose</li>
              <li>Attempt to reverse-engineer the prediction models</li>
              <li>Scrape, crawl, or otherwise extract data from the platform</li>
              <li>Interfere with or disrupt the service</li>
              <li>Create multiple accounts</li>
            </ul>
          </section>

          <section>
            <h3 className="text-text-primary font-semibold mb-2">9. Account Termination</h3>
            <p>
              We reserve the right to suspend or terminate your account at any time, with or
              without cause, with or without notice. Upon termination, your right to use the
              service will immediately cease.
            </p>
          </section>

          <section>
            <h3 className="text-text-primary font-semibold mb-2">10. Limitation of Liability</h3>
            <p>
              To the fullest extent permitted by law, the platform shall not be liable for any
              indirect, incidental, special, consequential, or punitive damages, including
              without limitation, loss of profits or data, arising from your use of the service.
            </p>
          </section>

          <section>
            <h3 className="text-text-primary font-semibold mb-2">11. Changes to Terms</h3>
            <p>
              We reserve the right to modify these terms at any time. Continued use of the
              platform after changes constitutes acceptance of the updated terms. Users may be
              required to re-accept updated terms.
            </p>
          </section>
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-border flex justify-end gap-3">
          {canDismiss && (
            <button
              onClick={onClose}
              className="btn btn-secondary px-5"
            >
              Cancel
            </button>
          )}
          <button
            onClick={onAccept}
            className="btn btn-primary px-5"
          >
            I Agree
          </button>
        </div>
      </div>
    </div>
  )
}
