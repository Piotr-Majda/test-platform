import { useLayoutEffect, useEffect, type ReactNode } from 'react'
import { useSubHeaderSlot } from './SubHeader'

/** Renders `children` in the sticky band under the main app header. */
export function PageSubHeader({ children }: { children: ReactNode }) {
  const { setSubHeader } = useSubHeaderSlot()

  useLayoutEffect(() => {
    setSubHeader(children)
  })

  useEffect(() => {
    return () => setSubHeader(null)
  }, [setSubHeader])

  return null
}
