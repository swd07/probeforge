/** Display formatting of the hybrid's explanation for the technician (D52): a repeated step prefix removed, readings
 * as numbers with units, hyphens restored in compounds. The run record keeps the text exactly as
 * the model and the frozen render() produced it, and the explanation check scores that text; only the page shows it
 * tidied. */

/** render() writes "Step N:" before each evidence sentence, and the model often starts the sentence with "Step N"
 * itself: "Step 20: Step 20 measured ..." becomes "Step 20: Measured ...". */
export function dedupeSteps(text: string): string {
  return text.replace(/\bStep (\d+): (?:(?:at|in) )?step \1\b[,:]?\s*(\w)?/gi,
    (_m, n: string, first?: string) => `Step ${n}: ${first ? first.toUpperCase() : ""}`);
}

const UNITS: Record<string, number> = {
  zero: 0, one: 1, two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7, eight: 8, nine: 9, ten: 10, eleven: 11,
  twelve: 12, thirteen: 13, fourteen: 14, fifteen: 15, sixteen: 16, seventeen: 17, eighteen: 18, nineteen: 19,
  twenty: 20, thirty: 30, forty: 40, fifty: 50, sixty: 60, seventy: 70, eighty: 80, ninety: 90,
};
const WORD = `(?:${Object.keys(UNITS).join("|")})`;
const SPELLED = new RegExp(String.raw`\b(${WORD}(?:(?:[\s-]+|\s+and\s+)(?:${WORD}|hundred))*)\s+(volts?|ohms?)\b`, "gi");

/** "two hundred eight" -> 208, up to 999; null when the words do not form a number. */
function wordsToNumber(words: string): number | null {
  let n = 0;
  for (const w of words.toLowerCase().split(/[\s-]+/).filter((x) => x && x !== "and")) {
    if (w === "hundred") {
      if (n === 0 || n > 9) return null;
      n *= 100;
    } else if (w in UNITS) {
      n += UNITS[w];
    } else return null;
  }
  return n <= 999 ? n : null;
}

/** The model sometimes spells readings out ("about two hundred eight volts"): shown as "about 208 V" ("0 ohm" for
 * ohms, the unit the app uses elsewhere). Only number words followed by a unit are changed. */
export function readingsAsNumbers(text: string): string {
  return text.replace(SPELLED, (m, words: string, unit: string) => {
    const n = wordsToNumber(words);
    return n === null ? m : `${n} ${unit.toLowerCase().startsWith("volt") ? "V" : "ohm"}`;
  });
}

// compounds the model writes apart under the prompt's no-dashes rule (from the recorded texts)
const COMPOUNDS: [RegExp, string][] = [
  [/\b(de|re) (energi[sz]\w*)/gi, "$1-$2"],
  [/\b(fault) (free)\b/gi, "$1-$2"],
  [/\b(cut) ?(off) (contacts?)\b/gi, "$1-$2 $3"], // the noun, also "cutoff contact"; "cut off the supply" stays
];

export function restoreHyphens(text: string): string {
  return COMPOUNDS.reduce((s, [re, to]) => s.replace(re, to), text);
}

export function tidyExplanation(text: string): string {
  return restoreHyphens(readingsAsNumbers(dedupeSteps(text)));
}
