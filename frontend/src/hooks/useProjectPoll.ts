import { useEffect } from "react"
import type { ProjectAction } from "../types"

/** Poll GET detail ~1s while action === "wait". Stops on unmount or other actions. */
export function useProjectPoll(
  projectId: string | undefined,
  action: ProjectAction | undefined,
  onTick: () => Promise<void>,
): void {
  useEffect(() => {
    if (!projectId || action !== "wait") return
    const timer = window.setInterval(() => {
      void onTick()
    }, 1000)
    return () => window.clearInterval(timer)
  }, [projectId, action, onTick])
}
