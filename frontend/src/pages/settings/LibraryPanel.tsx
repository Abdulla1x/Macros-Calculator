import FoodLibrarySection from '../../components/settings/FoodLibrarySection'
import SavedMealsSection from '../../components/settings/SavedMealsSection'
import { useSettingsPanel } from './panelContext'

/** Everything the app has remembered on your behalf, in one place to correct.
 *
 * Both sections here write straight to the server, so no Save bar ever appears
 * on this tab.
 */
export default function LibraryPanel() {
  const { onRejected } = useSettingsPanel()

  return (
    <div className="space-y-6">
      <FoodLibrarySection onRejected={onRejected} />
      <SavedMealsSection />
    </div>
  )
}
