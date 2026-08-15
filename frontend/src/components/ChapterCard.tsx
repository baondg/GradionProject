import { AuthImage } from "./AuthImage"

export function ChapterCard({
  name,
  prompt,
  illustrationUrl,
  waiting,
}: {
  name: string
  prompt: string
  illustrationUrl: string | null
  waiting: boolean
}) {
  return (
    <article className="entity-card">
      <div className={`art chapter${illustrationUrl ? "" : " pending"}`}>
        {illustrationUrl ? (
          <AuthImage src={illustrationUrl} alt={`Illustration for ${name}`} />
        ) : waiting ? (
          <div className="pending-inner">
            <span className="spinner" />
            <div className="gen-caption">Generating illustration…</div>
          </div>
        ) : (
          <span className="placeholder-label muted">Not generated yet</span>
        )}
      </div>
      <div className="body">
        <h5>{name}</h5>
        <p>{prompt}</p>
      </div>
    </article>
  )
}
