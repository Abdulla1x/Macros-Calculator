import AccountSection from '../../components/settings/AccountSection'

/** Sign-in, export, and deletion.
 *
 * Off the tab bar deliberately, and reached by a link instead: Danger zone
 * should not sit one mis-tap away from the tab you were aiming at. Writes
 * immediately, so no Save bar appears here either.
 */
export default function AccountPanel() {
  return (
    <div className="space-y-6">
      <AccountSection />
    </div>
  )
}
