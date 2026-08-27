import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../api/client'
import { useAuth } from '../../auth/AuthContext'
import { fieldClass } from './fieldClass'

export default function AccountSection() {
  const { user, changePassword, deleteAccount } = useAuth()
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [passwordStatus, setPasswordStatus] = useState<
    'idle' | 'saving' | 'saved' | 'error'
  >('idle')
  const [passwordError, setPasswordError] = useState('')
  const [exportError, setExportError] = useState('')
  const [confirmingDelete, setConfirmingDelete] = useState(false)
  const [deletePassword, setDeletePassword] = useState('')
  const [deleteStatus, setDeleteStatus] = useState<'idle' | 'deleting' | 'error'>('idle')
  const [deleteError, setDeleteError] = useState('')

  const submitPassword = async (event: React.FormEvent) => {
    event.preventDefault()
    if (newPassword.length < 8) {
      setPasswordStatus('error')
      setPasswordError('New password must be at least 8 characters.')
      return
    }
    if (newPassword !== confirmPassword) {
      setPasswordStatus('error')
      setPasswordError('New passwords do not match.')
      return
    }
    setPasswordStatus('saving')
    try {
      await changePassword(currentPassword, newPassword)
      setPasswordStatus('saved')
      setCurrentPassword('')
      setNewPassword('')
      setConfirmPassword('')
    } catch (err) {
      setPasswordStatus('error')
      setPasswordError(err instanceof Error ? err.message : 'Password change failed')
    }
  }

  const exportAll = async () => {
    setExportError('')
    try {
      await api.downloadExportAll()
    } catch (err) {
      setExportError(err instanceof Error ? err.message : 'Export failed')
    }
  }

  const submitDelete = async (event: React.FormEvent) => {
    event.preventDefault()
    setDeleteStatus('deleting')
    try {
      await deleteAccount(deletePassword)
      // AuthContext clears the user, so RequireAuth redirects to the login page.
    } catch (err) {
      setDeleteStatus('error')
      setDeleteError(err instanceof Error ? err.message : 'Account deletion failed')
    }
  }

  return (
    <>
      <section className="rounded-xl border border-slate-800 bg-slate-900 p-5">
        <h2 className="mb-1 font-semibold">Account</h2>
        <p className="mb-1 text-sm text-slate-400">Signed in as {user?.email}</p>
        {/* The only durable way back to the release notes. The pop-up links there
            too, but it is dismissible and then gone -- an entry point that exists
            only inside a thing you just closed is not an entry point. */}
        <p className="mb-4 text-sm text-ink-faint">
          <Link to="/whats-new" className="text-emerald-400 hover:text-emerald-300">
            What’s new
          </Link>{' '}
          — every release note, newest first.
        </p>

        <form onSubmit={submitPassword} className="max-w-sm space-y-3">
          <label className="block text-sm">
            <span className="mb-1 block text-slate-400">Current password</span>
            <input
              type="password"
              autoComplete="current-password"
              required
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              className={fieldClass}
            />
          </label>
          <label className="block text-sm">
            <span className="mb-1 block text-slate-400">New password</span>
            <input
              type="password"
              autoComplete="new-password"
              required
              minLength={8}
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              className={fieldClass}
            />
          </label>
          <label className="block text-sm">
            <span className="mb-1 block text-slate-400">Confirm new password</span>
            <input
              type="password"
              autoComplete="new-password"
              required
              minLength={8}
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              className={fieldClass}
            />
          </label>
          <div className="flex items-center gap-3">
            <button
              type="submit"
              disabled={passwordStatus === 'saving'}
              className="rounded-lg border border-slate-700 px-4 py-2 text-sm text-slate-200 hover:border-emerald-500 hover:text-emerald-300 disabled:opacity-60"
            >
              {passwordStatus === 'saving' ? 'Changing…' : 'Change password'}
            </button>
            {passwordStatus === 'saved' && (
              <span className="text-sm text-emerald-400">Password changed ✓</span>
            )}
            {passwordStatus === 'error' && (
              <span className="text-sm text-rose-400">{passwordError}</span>
            )}
          </div>
        </form>

        <div className="mt-5 border-t border-slate-800 pt-4">
          <p className="mb-2 text-sm text-slate-400">
            Download everything stored for this account — meals, food library, saved
            meal templates, weight entries, water logs, step counts, supplements and
            the doses you ticked, calorie plans, body profile, goals and AI analyses
            — as a single JSON file.
          </p>
          <button
            onClick={exportAll}
            className="rounded-lg border border-slate-700 px-4 py-2 text-sm text-slate-200 hover:border-emerald-500 hover:text-emerald-300"
          >
            Download all my data (JSON)
          </button>
          {exportError && <p className="mt-2 text-sm text-rose-400">{exportError}</p>}
        </div>
      </section>

      <section className="rounded-xl border border-rose-900/60 bg-slate-900 p-5">
        <h2 className="mb-1 font-semibold text-rose-300">Danger zone</h2>
        <p className="mb-4 text-sm text-slate-400">
          Deleting your account permanently removes all meals, foods, meal templates,
          weight entries, water logs, step counts, supplements and their check-offs,
          calorie plans, your body profile, goals and AI analyses. This cannot be
          undone.
        </p>
        {!confirmingDelete ? (
          <button
            onClick={() => setConfirmingDelete(true)}
            className="rounded-lg border border-rose-700 px-4 py-2 text-sm text-rose-300 hover:bg-rose-500/10"
          >
            Delete account…
          </button>
        ) : (
          <form onSubmit={submitDelete} className="max-w-sm space-y-3">
            <label className="block text-sm">
              <span className="mb-1 block text-slate-400">
                Enter your password to confirm
              </span>
              <input
                type="password"
                autoComplete="current-password"
                required
                value={deletePassword}
                onChange={(e) => setDeletePassword(e.target.value)}
                className={fieldClass}
              />
            </label>
            <div className="flex items-center gap-3">
              <button
                type="submit"
                disabled={deleteStatus === 'deleting'}
                className="rounded-lg bg-rose-600 px-4 py-2 text-sm font-semibold text-white hover:bg-rose-500 disabled:opacity-60"
              >
                {deleteStatus === 'deleting'
                  ? 'Deleting…'
                  : 'Permanently delete my account'}
              </button>
              <button
                type="button"
                onClick={() => {
                  setConfirmingDelete(false)
                  setDeletePassword('')
                  setDeleteStatus('idle')
                }}
                className="text-sm text-slate-400 hover:text-slate-200"
              >
                Cancel
              </button>
            </div>
            {deleteStatus === 'error' && (
              <p className="text-sm text-rose-400">{deleteError}</p>
            )}
          </form>
        )}
      </section>
    </>
  )
}
