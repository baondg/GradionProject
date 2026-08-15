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
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let revoked = false
    let objectUrl: string | null = null
    setBlobUrl(null)
    setFailed(false)
    void (async () => {
      try {
        const response = await fetch(src, { headers })
        if (!response.ok) {
          if (!revoked) setFailed(true)
          return
        }
        const blob = await response.blob()
        if (revoked) return
        if (blob.size === 0) {
          setFailed(true)
          return
        }
        objectUrl = URL.createObjectURL(blob)
        setBlobUrl(objectUrl)
      } catch {
        if (!revoked) setFailed(true)
      }
    })()
    return () => {
      revoked = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [src, headers])

  if (failed) {
    return (
      <span className="img-fallback" role="img" aria-label={alt}>
        Image unavailable
      </span>
    )
  }
  if (!blobUrl) {
    return <span className="spinner" aria-hidden="true" />
  }
  return (
    <img
      src={blobUrl}
      alt={alt}
      onError={() => {
        setFailed(true)
        setBlobUrl(null)
      }}
    />
  )
}
