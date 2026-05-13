/**
 * Shared inline styles for authentication form pages.
 * Using inline styles to keep the project self-contained without a CSS framework.
 */

import type { CSSProperties } from 'react'

export const formStyles: Record<string, CSSProperties> = {
  pageContainer: {
    display: 'flex',
    justifyContent: 'center',
    alignItems: 'center',
    minHeight: '100vh',
    padding: '24px',
    backgroundColor: '#f0f2f5',
  },
  card: {
    backgroundColor: '#fff',
    borderRadius: '12px',
    padding: '40px',
    width: '100%',
    maxWidth: '420px',
    boxShadow: '0 4px 24px rgba(0,0,0,0.08)',
  },
  title: {
    fontSize: '1.75rem',
    fontWeight: 700,
    color: '#1a1a2e',
    marginBottom: '4px',
  },
  subtitle: {
    fontSize: '0.875rem',
    color: '#888',
    marginBottom: '28px',
  },
  fieldGroup: {
    marginBottom: '16px',
  },
  label: {
    display: 'block',
    fontSize: '0.875rem',
    fontWeight: 500,
    color: '#444',
    marginBottom: '6px',
  },
  input: {
    width: '100%',
    padding: '10px 14px',
    border: '1px solid #ddd',
    borderRadius: '8px',
    fontSize: '1rem',
    color: '#1a1a2e',
    backgroundColor: '#fafafa',
    outline: 'none',
    transition: 'border-color 0.2s',
  },
  inputError: {
    borderColor: '#e63946',
    backgroundColor: '#fff5f5',
  },
  fieldError: {
    fontSize: '0.8rem',
    color: '#e63946',
    marginTop: '4px',
  },
  errorBox: {
    padding: '12px 16px',
    backgroundColor: '#fff5f5',
    border: '1px solid #ffc9c9',
    borderRadius: '8px',
    color: '#c92a2a',
    fontSize: '0.875rem',
    marginBottom: '16px',
  },
  successBox: {
    padding: '12px 16px',
    backgroundColor: '#f0fff4',
    border: '1px solid #b2f2bb',
    borderRadius: '8px',
    color: '#2f9e44',
    fontSize: '0.875rem',
    marginBottom: '16px',
  },
  submitButton: {
    width: '100%',
    padding: '12px',
    backgroundColor: '#4361ee',
    color: '#fff',
    border: 'none',
    borderRadius: '8px',
    fontSize: '1rem',
    fontWeight: 600,
    cursor: 'pointer',
    marginTop: '8px',
    transition: 'background-color 0.2s',
  },
  submitButtonDisabled: {
    backgroundColor: '#a5b4fc',
    cursor: 'not-allowed',
  },
  links: {
    display: 'flex',
    justifyContent: 'center',
    alignItems: 'center',
    gap: '8px',
    marginTop: '20px',
    fontSize: '0.875rem',
  },
  link: {
    color: '#4361ee',
    textDecoration: 'none',
  },
  linkSeparator: {
    color: '#ccc',
  },
  stepIndicator: {
    display: 'flex',
    justifyContent: 'center',
    gap: '8px',
    marginBottom: '24px',
  },
  stepDot: {
    width: '8px',
    height: '8px',
    borderRadius: '50%',
    backgroundColor: '#ddd',
  },
  stepDotActive: {
    backgroundColor: '#4361ee',
  },
  passwordHint: {
    fontSize: '0.78rem',
    color: '#888',
    marginTop: '4px',
    lineHeight: 1.4,
  },
}
