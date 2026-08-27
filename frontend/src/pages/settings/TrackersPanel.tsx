import StepsSection from '../../components/settings/StepsSection'
import SupplementsSection from '../../components/settings/SupplementsSection'
import WaterSection from '../../components/settings/WaterSection'
import { useSettingsPanel } from './panelContext'

/** The three daily trackers, and the one place two save models meet.
 *
 * Water and Steps are columns on the settings row, so they feed the Save bar
 * like everything on Goals and Body. Supplements is its own table with its own
 * endpoints and writes immediately. That split is not hidden: the bar appears
 * for the first pair and stays away for the second, so the behaviour teaches
 * which is which without a sentence explaining it.
 */
export default function TrackersPanel() {
  const { settings, update, onRejected } = useSettingsPanel()

  return (
    <div className="space-y-6">
      <WaterSection settings={settings} update={update} onRejected={onRejected} />
      <StepsSection settings={settings} update={update} onRejected={onRejected} />
      <SupplementsSection onRejected={onRejected} />
    </div>
  )
}
