export type NecoMood = "ok" | "think" | "alert";

/** Neco: quadrado bordô com dois olhos. O humor muda só os olhos. */
export function Neco({ size = 32, mood = "ok", invert = false }: { size?: number; mood?: NecoMood; invert?: boolean }) {
  const bg = invert ? "#fff" : "var(--bordo)";
  const fg = invert ? "var(--bordo)" : "#fff";
  const y = mood === "think" ? 13.5 : 18;
  return (
    <svg className="neco" viewBox="0 0 36 36" width={size} height={size} role="img" aria-label="Neco">
      <rect width="36" height="36" rx="10" fill={bg} />
      {mood === "alert" ? (
        <>
          <rect x="10" y="17" width="6" height="2.6" rx="1.3" fill={fg} />
          <rect x="20" y="17" width="6" height="2.6" rx="1.3" fill={fg} />
        </>
      ) : (
        <>
          <circle cx="13" cy={y} r="2.6" fill={fg} />
          <circle cx="23" cy={y} r="2.6" fill={fg} />
        </>
      )}
    </svg>
  );
}
