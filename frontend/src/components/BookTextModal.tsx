import { useEffect, useRef } from "react"

export function BookTextModal({
  text,
  onClose,
}: {
  text: string
  onClose: () => void
}) {
  const closeRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    closeRef.current?.focus()
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose()
    }
    document.addEventListener("keydown", onKey)
    return () => document.removeEventListener("keydown", onKey)
  }, [onClose])

  return (
    <div
      className="modal-overlay"
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose()
      }}
    >
      <div
        className="modal-box"
        role="dialog"
        aria-modal="true"
        aria-labelledby="book-modal-title"
      >
        <div className="modal-head">
          <h4 id="book-modal-title">Full book text</h4>
          <button
            ref={closeRef}
            type="button"
            className="modal-close"
            onClick={onClose}
            aria-label="Close"
          >
            ✕
          </button>
        </div>
        <div className="modal-body">{text}</div>
      </div>
    </div>
  )
}
