// What a card must show the engineer, as code wrote it: every flag verbatim, in order.

export function Flags({ flags }: { flags: readonly string[] }) {
  if (flags.length === 0) return null;
  return (
    <ul className="flags">
      {flags.map((flag) => (
        <li key={flag}>{flag}</li>
      ))}
    </ul>
  );
}
