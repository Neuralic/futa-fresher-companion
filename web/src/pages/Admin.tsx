import { useRef, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { apiPost } from '../api/client';
import type { Announcement, AnnouncementScope, User } from '../api/types';
import { useAuth } from '../lib/auth';
import {
  adminGate,
  BODY_MAX,
  buildAnnouncement,
  charCount,
  publishError,
  SCOPE_LABELS,
  scopesForRole,
  targetPicker,
  TITLE_MAX,
  validateAnnouncement,
  type ComposerField,
  type ComposerValues,
} from '../lib/composerView';
import type { FieldErrors } from '../lib/authView';
import { readComposerChoices } from '../lib/offline';
import { useCachedRows } from '../lib/useCachedRows';

// Admin tools. The role comes from the server (/auth/me), never from the token. The server
// checks it again on every publish, so this gate only keeps the screen out of the wrong hands.
export default function Admin() {
  const { status, user } = useAuth();
  const gate = adminGate(status, user);

  if (gate === 'loading') return <p className="muted">Loading…</p>;
  if (gate === 'signed-out') {
    return (
      <>
        <h1>Admin</h1>
        <p>Log in to continue.</p>
        <p>
          <Link to="/login">Log in</Link>
        </p>
      </>
    );
  }
  if (gate === 'no-profile' || !user) {
    return (
      <>
        <h1>Admin</h1>
        <p role="alert">
          Your account details could not be loaded. Check your connection and reload the page.
        </p>
      </>
    );
  }
  if (gate === 'forbidden') {
    return (
      <>
        <h1>Admin</h1>
        <p>Admins only.</p>
      </>
    );
  }
  return <Composer user={user} />;
}

function Composer({ user }: { user: User }) {
  const scopes = scopesForRole(user.role);
  const choices = useCachedRows(readComposerChoices);

  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');
  const [scope, setScope] = useState<AnnouncementScope>(scopes[0]);
  const [chosenId, setChosenId] = useState('');
  const [expires, setExpires] = useState('');
  const [errors, setErrors] = useState<FieldErrors<ComposerField>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [published, setPublished] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  // State updates are not instant, so a quick double click needs this guard as well.
  const inFlight = useRef(false);

  const cached = choices.result.state === 'ready' ? choices.result.value : null;
  const picker = targetPicker(user, scope, cached?.faculties ?? [], cached?.departments ?? []);
  // A locked picker always shows the user's own faculty or department.
  const targetId = picker?.locked ? picker.selectedId : chosenId;

  function changeScope(next: AnnouncementScope) {
    setScope(next);
    setChosenId('');
    setErrors((e) => ({ ...e, scope: undefined, target: undefined }));
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (inFlight.current) return;
    setPublished(null);
    setFormError(null);

    const values: ComposerValues = { title, body, scope, targetId, expires };
    const problems = validateAnnouncement(values, user.role, Date.now());
    if (picker?.problem && !problems.target) problems.target = picker.problem;
    setErrors(problems);
    if (Object.keys(problems).length > 0) return;

    if (!navigator.onLine) {
      setFormError(publishError(new Error('offline'), false));
      return;
    }

    inFlight.current = true;
    setSending(true);
    try {
      const sent = buildAnnouncement(values);
      const created = await apiPost<Announcement>('/announcements', sent, { auth: true });
      setPublished(created.title);
      setTitle('');
      setBody('');
      setScope(scopes[0]);
      setChosenId('');
      setExpires('');
      setErrors({});
    } catch (error) {
      // A 401 has already signed the user out and sent them to the login page.
      setFormError(publishError(error, navigator.onLine));
    } finally {
      inFlight.current = false;
      setSending(false);
    }
  }

  const titleCount = charCount(title);
  const bodyCount = charCount(body);
  const pickerHelp =
    picker && !picker.locked && choices.result.state === 'error'
      ? 'The list could not be read on this device.'
      : picker && !picker.locked && cached && picker.options.length === 0
        ? 'No saved list on this device yet. Connect to the internet and let the app sync first.'
        : null;

  return (
    <>
      <h1>New announcement</h1>
      <p className="muted">Plain text only. It is published straight away.</p>

      {published && (
        <p role="status">
          Published: “{published}”.
        </p>
      )}

      <form onSubmit={submit} noValidate className="form">
        <div className="field">
          <label htmlFor="ann-title">Title</label>
          <input
            id="ann-title"
            name="title"
            autoComplete="off"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            aria-invalid={Boolean(errors.title)}
            aria-describedby={errors.title ? 'ann-title-count ann-title-error' : 'ann-title-count'}
          />
          <p className="hint" id="ann-title-count">
            {titleCount} / {TITLE_MAX} characters
          </p>
          {errors.title && (
            <p id="ann-title-error" className="field-error">
              {errors.title}
            </p>
          )}
        </div>

        <div className="field">
          <label htmlFor="ann-body">Announcement</label>
          <textarea
            id="ann-body"
            name="body"
            rows={8}
            value={body}
            onChange={(e) => setBody(e.target.value)}
            aria-invalid={Boolean(errors.body)}
            aria-describedby={errors.body ? 'ann-body-count ann-body-error' : 'ann-body-count'}
          />
          <p className="hint" id="ann-body-count">
            {bodyCount} / {BODY_MAX} characters
          </p>
          {errors.body && (
            <p id="ann-body-error" className="field-error">
              {errors.body}
            </p>
          )}
        </div>

        <div className="field">
          <label htmlFor="ann-scope">Who is it for?</label>
          <select
            id="ann-scope"
            value={scope}
            disabled={scopes.length === 1}
            onChange={(e) => changeScope(e.target.value as AnnouncementScope)}
            aria-invalid={Boolean(errors.scope)}
          >
            {scopes.map((option) => (
              <option key={option} value={option}>
                {SCOPE_LABELS[option]}
              </option>
            ))}
          </select>
          {errors.scope && <p className="field-error">{errors.scope}</p>}
        </div>

        {picker && (
          <div className="field">
            <label htmlFor="ann-target">{picker.label}</label>
            <select
              id="ann-target"
              value={targetId}
              disabled={picker.locked || choices.result.state === 'loading'}
              onChange={(e) => setChosenId(e.target.value)}
              aria-invalid={Boolean(errors.target)}
              aria-describedby={
                errors.target ? 'ann-target-error' : pickerHelp ? 'ann-target-help' : undefined
              }
            >
              {!picker.locked && (
                <option value="">
                  {choices.result.state === 'loading' ? 'Loading…' : `Choose a ${picker.label.toLowerCase()}`}
                </option>
              )}
              {picker.options.map((option) => (
                <option key={option.id} value={option.id}>
                  {option.name}
                </option>
              ))}
            </select>
            {pickerHelp && !errors.target && (
              <p id="ann-target-help" className="hint">
                {pickerHelp}
              </p>
            )}
            {errors.target && (
              <p id="ann-target-error" className="field-error">
                {errors.target}
              </p>
            )}
          </div>
        )}

        <div className="field">
          <label htmlFor="ann-expires">Expires (optional)</label>
          <p className="hint" id="ann-expires-hint">
            Your device’s time. Leave empty for no expiry.
          </p>
          <input
            id="ann-expires"
            name="expires"
            type="datetime-local"
            value={expires}
            onChange={(e) => setExpires(e.target.value)}
            aria-invalid={Boolean(errors.expires)}
            aria-describedby={
              errors.expires ? 'ann-expires-hint ann-expires-error' : 'ann-expires-hint'
            }
          />
          {errors.expires && (
            <p id="ann-expires-error" className="field-error">
              {errors.expires}
            </p>
          )}
        </div>

        {formError && (
          <p role="alert" className="field-error">
            {formError}
          </p>
        )}

        <button type="submit" disabled={sending}>
          {sending ? 'Publishing…' : 'Publish'}
        </button>
      </form>
    </>
  );
}
