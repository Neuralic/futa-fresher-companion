import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { apiPost } from '../api/client';
import { friendlyError, LEVEL_OPTIONS, validateRegister, type FieldErrors } from '../lib/authView';
import { readDepartmentChoices } from '../lib/offline';
import { useCachedRows } from '../lib/useCachedRows';

type Field = 'fullName' | 'email' | 'password' | 'matric';

// Sign-up is open. The server always makes a student account. Nothing here sets a role.
export default function Register() {
  const navigate = useNavigate();
  const departments = useCachedRows(readDepartmentChoices);

  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [matric, setMatric] = useState('');
  const [departmentId, setDepartmentId] = useState('');
  const [level, setLevel] = useState('');
  const [errors, setErrors] = useState<FieldErrors<Field>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (sending) return;
    const problems = validateRegister({ fullName, email, password, matric });
    setErrors(problems);
    setFormError(null);
    if (Object.keys(problems).length > 0) return;

    setSending(true);
    try {
      // Optional fields are left out when blank. The server never gets empty strings for them.
      await apiPost('/auth/register', {
        full_name: fullName.trim(),
        email: email.trim(),
        password,
        ...(matric.trim() ? { matric_no: matric.trim() } : {}),
        ...(departmentId ? { department_id: departmentId } : {}),
        ...(level ? { level: Number(level) } : {}),
      });
      // Registration returns no token. The user logs in next.
      navigate('/login', { state: { registered: true } });
    } catch (error) {
      setFormError(friendlyError(error, navigator.onLine));
    } finally {
      // The password is not kept after submit, whether it worked or not.
      setPassword('');
      setSending(false);
    }
  }

  const departmentHelp =
    departments.result.state === 'error'
      ? 'Departments could not be read on this device. You can skip this and add it later.'
      : departments.result.state === 'ready' && departments.result.value.length === 0
        ? 'Your department list is not saved on this device yet. You can skip this and add it later.'
        : null;

  return (
    <>
      <h1>Create an account</h1>
      <p className="muted">
        Optional. Your account is for admin features only. Everything else works without it.
      </p>

      <form onSubmit={submit} noValidate className="form">
        <div className="field">
          <label htmlFor="reg-name">Full name</label>
          <input
            id="reg-name"
            name="full_name"
            autoComplete="name"
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            aria-invalid={Boolean(errors.fullName)}
            aria-describedby={errors.fullName ? 'reg-name-error' : undefined}
          />
          {errors.fullName && (
            <p id="reg-name-error" className="field-error">
              {errors.fullName}
            </p>
          )}
        </div>

        <div className="field">
          <label htmlFor="reg-email">Email</label>
          <input
            id="reg-email"
            name="email"
            type="email"
            inputMode="email"
            autoComplete="username"
            autoCapitalize="none"
            spellCheck={false}
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            aria-invalid={Boolean(errors.email)}
            aria-describedby={errors.email ? 'reg-email-error' : undefined}
          />
          {errors.email && (
            <p id="reg-email-error" className="field-error">
              {errors.email}
            </p>
          )}
        </div>

        <div className="field">
          <label htmlFor="reg-password">Password</label>
          <p className="hint" id="reg-password-hint">
            8 to 128 characters.
          </p>
          <input
            id="reg-password"
            name="password"
            type="password"
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            aria-invalid={Boolean(errors.password)}
            aria-describedby={
              errors.password ? 'reg-password-hint reg-password-error' : 'reg-password-hint'
            }
          />
          {errors.password && (
            <p id="reg-password-error" className="field-error">
              {errors.password}
            </p>
          )}
        </div>

        <div className="field">
          <label htmlFor="reg-matric">Matric number (optional)</label>
          <p className="hint" id="reg-matric-hint">
            A label only. It is not checked.
          </p>
          <input
            id="reg-matric"
            name="matric_no"
            autoComplete="off"
            value={matric}
            onChange={(e) => setMatric(e.target.value)}
            aria-invalid={Boolean(errors.matric)}
            aria-describedby={errors.matric ? 'reg-matric-hint reg-matric-error' : 'reg-matric-hint'}
          />
          {errors.matric && (
            <p id="reg-matric-error" className="field-error">
              {errors.matric}
            </p>
          )}
        </div>

        <div className="field">
          <label htmlFor="reg-department">Department (optional)</label>
          <select
            id="reg-department"
            value={departmentId}
            disabled={departments.result.state === 'loading'}
            onChange={(e) => setDepartmentId(e.target.value)}
            aria-describedby={departmentHelp ? 'reg-department-help' : undefined}
          >
            <option value="">
              {departments.result.state === 'loading' ? 'Loading departments…' : 'Not set'}
            </option>
            {departments.result.state === 'ready' &&
              departments.result.value.map((department) => (
                <option key={department.id} value={department.id}>
                  {department.school
                    ? `${department.name} (${department.school})`
                    : department.name}
                </option>
              ))}
          </select>
          {departmentHelp && (
            <p id="reg-department-help" className="hint">
              {departmentHelp}
            </p>
          )}
        </div>

        <div className="field">
          <label htmlFor="reg-level">Level (optional)</label>
          <select id="reg-level" value={level} onChange={(e) => setLevel(e.target.value)}>
            <option value="">Not set</option>
            {LEVEL_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {option} Level
              </option>
            ))}
          </select>
        </div>

        {formError && (
          <p role="alert" className="field-error">
            {formError}
          </p>
        )}

        <button type="submit" disabled={sending}>
          {sending ? 'Creating account…' : 'Create account'}
        </button>
      </form>

      <p>
        Already have an account? <Link to="/login">Log in</Link>
      </p>
    </>
  );
}
