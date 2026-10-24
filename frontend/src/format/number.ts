// The one formatter for numbers the backend sends raw (P5-5). Everything the backend formats
// itself (the gap text, evidence summaries) is shown as it comes and never passes through here.
// Orders of magnitude, never false precision; float noise never reaches the screen.

const DASH = "—";
// below this a frequency is written in exponent form
const SMALLEST_DECIMAL = 0.001;

/** A frequency per year, to at most 2 significant figures: "0.1 /yr", "1e-5 /yr". */
export function frequency(value: number | null | undefined): string {
  if (value === null || value === undefined) return DASH;
  if (value === 0) return "0 /yr";
  const rounded = Number(value.toPrecision(2));
  if (Math.abs(rounded) >= SMALLEST_DECIMAL) return `${String(rounded)} /yr`;
  const [mantissa = "", exponent = ""] = rounded.toExponential(1).split("e");
  const trimmed = mantissa.replace(/\.0$/, "");
  return `${trimmed}e${exponent.replace(/^\+/, "")} /yr`;
}

/** A layer's probability of failure on demand, as the reference table stores it: "0.01". */
export function pfd(value: number | null | undefined): string {
  if (value === null || value === undefined) return DASH;
  return String(Number(value.toPrecision(12)));
}

/** A dollar amount: "$0.98"; a non-zero amount under a cent reads "<$0.01". */
export function money(value: number | null | undefined): string {
  if (value === null || value === undefined) return DASH;
  if (value > 0 && value < 0.01) return "<$0.01";
  const cents = Math.round((value + Number.EPSILON) * 100);
  return `$${(cents / 100).toFixed(2)}`;
}
