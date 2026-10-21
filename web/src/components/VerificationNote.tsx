import type { Faculty } from '../api/types';
import { formatUpdated, verificationLabel } from '../lib/academicsView';

// Every item shows its verification. The text says the status; the symbol is only a hint.
export default function VerificationNote({
  verification,
  updatedAt,
}: {
  verification: Faculty['verification'];
  updatedAt: string;
}) {
  const label = verificationLabel(verification.status);
  return (
    <div className="verification">
      <p>
        <span aria-hidden="true">{label.symbol}</span> {label.text}{' '}
        <span className="muted">· {formatUpdated(updatedAt)}</span>
      </p>
      <details>
        <summary>Source</summary>
        <p>{verification.source || 'No source recorded'}</p>
      </details>
    </div>
  );
}
