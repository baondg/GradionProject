import { useEffect, useState } from "react"
import { useAuth } from "../auth"

export function AuthImage({
  src,
  alt,
}: {
  src: string
  alt: string
}) {
  const { headers } = useAuth()
  const [blobUrl, setBlobUrl] = useState<string | null>(null)

  useEffect(() => {
    let revoked = false
    let objectUrl: string | null = null
    void (async () => {
      try {
        const response = await fetch(src, { headers })
        if (!response.ok) return
        const blob = await response.blob()
        if (revoked) return
        objectUrl = URL.createObjectURL(blob)
        setBlobUrl(objectUrl)
      } catch {
        /* keep placeholder */
      }
    })()
    return () => {
      revoked = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [src, headers])

  if (!blobUrl) {
    return <span className="spinner" aria-hidden="true" />
  }
  return <img src={blobUrl} alt={alt} />
}
