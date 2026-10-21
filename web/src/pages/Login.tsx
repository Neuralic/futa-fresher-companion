import { useState, type FormEvent } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../lib/auth';
import { friendlyError, type FieldErrors, validateLogin } from '../lib/authView';

type Field = 'email' | 'password';

// Login is optional. Only admin features need it, so the rest of the app never asks for it.
export default function Login() {
  const { signIn } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const justRegistered = Boolean((location.state as { registered?: boolean } | null)?.registered);

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [errors, setErrors] = useState<FieldErrors<Field>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (sending) return;
    const problems = validateLogin({ email, password });
    setErrors(problems);
    setFormError(null);
    if (Object.keys(problems).length > 0) return;

    setSending(true);
    try {
      await signIn(email.trim(), password);
      navigate('/');
    } catch (error) {
      setFormError(friendlyError(error, navigator.onLine));
    } finally {
      // The password is not kept after submit, whether it worked or not.
      setPassword('');
      setSending(false);
    }
  }

  return (
    <>
      <h1>Log in</h1>
      {justRegistered && (
        <p role="status">Your account is ready. Log in to continue.</p>
      )}
      <p className="muted">Log in to use admin features. Everything else works without it.</p>

      <form onSubmit={submit} noValidate className="form">
        <div className="field">
          <label htmlFor="login-email">Email</label>
          <input
            id="login-email"
            name="email"
            type="email"
            inputMode="email"
            autoComplete="username"
            autoCapitalize="none"
            spellCheck={false}
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            aria-invalid={Boolean(errors.email)}
            aria-describedby={errors.email ? 'login-email-error' : undefined}
          />
          {errors.email && (
            <p id="login-email-error" className="field-error">
              {errors.email}
            </p>
          )}
        </div>

        <div className="field">
          <label htmlFor="login-password">Password</label>
          <input
            id="login-password"
            name="password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            aria-invalid={Boolean(errors.password)}
            aria-describedby={errors.password ? 'login-password-error' : undefined}
          />
          {errors.password && (
            <p id="login-password-error" className="field-error">
              {errors.password}
            </p>
          )}
        </div>

        {formError && (
          <p role="alert" className="field-error">
            {formError}
          </p>
        )}

        <button type="submit" disabled={sending}>
          {sending ? 'Logging in…' : 'Log in'}
        </button>
      </form>

      <p>
        New here? <Link to="/register">Create an account</Link>
      </p>
    </>
  );
}
