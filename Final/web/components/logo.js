// CareerMirror mark (CIBrand.md section 2): a circle split down the middle,
// a solid half and its translucent reflection. Colours follow the theme tokens.
// Standalone SVG files for print and favicon come with the brand-assets task.
export function LogoMark({ className = "size-7" }) {
  return (
    <svg viewBox="0 0 100 100" className={className} aria-hidden="true">
      <path d="M47 4 A46 46 0 0 0 47 96 Z" fill="var(--color-primary)" />
      <path d="M53 4 A46 46 0 0 1 53 96 Z" fill="var(--color-primary)" fillOpacity="0.35" />
      <circle cx="32" cy="30" r="7" fill="var(--color-bg)" fillOpacity="0.9" />
    </svg>
  );
}

export function Logo({ name = "CareerMirror" }) {
  // Wordmark: first word bold, the rest regular, in the Latin brand font.
  const split = name.match(/^([A-Z][a-z]+)(.*)$/);
  const [first, rest] = split ? [split[1], split[2]] : [name, ""];
  return (
    <span className="inline-flex items-center gap-2">
      <LogoMark />
      <span className="font-[family-name:var(--font-latin-first)] text-h3 text-text">
        <span className="font-bold">{first}</span>
        <span className="font-normal">{rest}</span>
      </span>
    </span>
  );
}
