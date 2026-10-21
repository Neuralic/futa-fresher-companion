import { describe, expect, it } from 'vitest';
import { ApiError } from '../api/client';
import { friendlyError, passwordLength, validateLogin, validateRegister } from './authView';

describe('validateLogin', () => {
  it('accepts a valid email and a password', () => {
    expect(validateLogin({ email: 'ada@example.com', password: 'anything' })).toEqual({});
  });

  it('asks for an email, and checks its shape', () => {
    expect(validateLogin({ email: '', password: 'x' }).email).toBe('Enter your email address.');
    expect(validateLogin({ email: 'not-an-email', password: 'x' }).email).toBe(
      'Enter a valid email address.',
    );
    expect(validateLogin({ email: 'a@b', password: 'x' }).email).toBe(
      'Enter a valid email address.',
    );
  });

  it('asks for a password, but does not check its length at login', () => {
    expect(validateLogin({ email: 'ada@example.com', password: '' }).password).toBe(
      'Enter your password.',
    );
    expect(validateLogin({ email: 'ada@example.com', password: 'x' })).toEqual({});
  });

  it('trims the email before checking it', () => {
    expect(validateLogin({ email: '  ada@example.com  ', password: 'x' })).toEqual({});
  });
});

describe('validateRegister', () => {
  const valid = {
    fullName: 'Ada Obi',
    email: 'ada@example.com',
    password: 'correct horse',
    matric: '',
  };

  it('accepts a complete form with the optional fields left blank', () => {
    expect(validateRegister(valid)).toEqual({});
  });

  it('requires a full name of at least 2 characters', () => {
    expect(validateRegister({ ...valid, fullName: ' A ' }).fullName).toBe(
      'Enter your full name (at least 2 characters).',
    );
    expect(validateRegister({ ...valid, fullName: 'Al' })).toEqual({});
  });

  it('accepts a password of exactly 8 and exactly 128 characters', () => {
    expect(validateRegister({ ...valid, password: 'a'.repeat(8) })).toEqual({});
    expect(validateRegister({ ...valid, password: 'a'.repeat(128) })).toEqual({});
  });

  it('rejects a password of 7 characters and of 129 characters', () => {
    expect(validateRegister({ ...valid, password: 'a'.repeat(7) }).password).toBe(
      'Use at least 8 characters.',
    );
    expect(validateRegister({ ...valid, password: 'a'.repeat(129) }).password).toBe(
      'Use no more than 128 characters.',
    );
  });

  it('counts characters, not UTF-16 units, so an emoji counts once', () => {
    expect(passwordLength('😀'.repeat(8))).toBe(8);
    expect(validateRegister({ ...valid, password: '😀'.repeat(8) })).toEqual({});
  });

  it('limits the matric number to 40 characters', () => {
    expect(validateRegister({ ...valid, matric: 'M'.repeat(40) })).toEqual({});
    expect(validateRegister({ ...valid, matric: 'M'.repeat(41) }).matric).toBe(
      'The matric number is too long.',
    );
  });

  it('checks the email the same way as login', () => {
    expect(validateRegister({ ...valid, email: 'nope' }).email).toBe(
      'Enter a valid email address.',
    );
  });
});

describe('friendlyError', () => {
  it('shows the server message for 401 and 409, which are already generic', () => {
    expect(friendlyError(new ApiError(401, 'Invalid email or password'), true)).toBe(
      'Invalid email or password',
    );
    expect(
      friendlyError(new ApiError(409, 'An account with this email or matric number already exists'), true),
    ).toBe('An account with this email or matric number already exists');
  });

  it('does not reveal, for an unknown email, that the account is missing', () => {
    const text = friendlyError(new ApiError(401, 'Invalid email or password'), true);

    expect(text).not.toMatch(/not (found|registered|exist)|no account|unknown/i);
  });

  it('gives a friendly text for 422, 429 and 503', () => {
    expect(friendlyError(new ApiError(422, 'Unprocessable Content'), true)).toBe(
      'Some details are not valid. Check the form and try again.',
    );
    expect(friendlyError(new ApiError(429, 'Too Many Requests'), true)).toBe(
      'Too many attempts. Wait a few minutes and try again.',
    );
    expect(friendlyError(new ApiError(503, 'x'), true)).toBe(
      'The service is busy right now. Try again shortly.',
    );
  });

  it('uses the Retry-After value for 503 when the server sends one', () => {
    expect(friendlyError(new ApiError(503, 'x', 5), true)).toBe(
      'The service is busy right now. Try again in 5 seconds.',
    );
  });

  it('says so when the device is offline, whatever the error', () => {
    expect(friendlyError(new TypeError('Failed to fetch'), false)).toBe(
      'You appear to be offline. Connect to the internet and try again.',
    );
    expect(friendlyError(new ApiError(500, 'x'), false)).toMatch(/offline/);
  });

  it('gives a network message when online but no answer came back', () => {
    expect(friendlyError(new TypeError('Failed to fetch'), true)).toBe(
      'Could not reach the server. Check your connection and try again.',
    );
  });

  it('falls back to a generic message for other server errors', () => {
    expect(friendlyError(new ApiError(500, 'Internal Server Error'), true)).toBe(
      'Something went wrong. Try again.',
    );
  });
});
