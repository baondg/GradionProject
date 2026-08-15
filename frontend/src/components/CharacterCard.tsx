import { AuthImage } from "./AuthImage"

export function CharacterCard({
  name,
  prompt,
  portraitUrl,
  waiting,
}: {
  name: string
  prompt: string
  portraitUrl: string | null
  waiting: boolean
}) {
  return (
    <article className="entity-card">
      <div className={`art${portraitUrl ? "" : " pending"}`}>
        {portraitUrl ? (
          <AuthImage src={portraitUrl} alt={`Portrait of ${name}`} />
        ) : waiting ? (
          <div className="pending-inner">
            <span className="spinner" />
            <div className="gen-caption">Generating portrait for {name}…</div>
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
