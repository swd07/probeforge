/** Display formatting of the hybrid's explanation for the technician (D52). The run record keeps the text exactly as
 * the model and the frozen render() produced it, and the explanation check scores that text; only the page shows it
 * tidied. */

/** render() writes "Step N:" before each evidence sentence, and the model often starts the sentence with "Step N"
 * itself: "Step 20: Step 20 measured ..." becomes "Step 20: Measured ...". */
export function dedupeSteps(text: string): string {
  return text.replace(/\bStep (\d+): (?:(?:at|in) )?step \1\b[,:]?\s*(\w)?/gi,
    (_m, n: string, first?: string) => `Step ${n}: ${first ? first.toUpperCase() : ""}`);
}

export function tidyExplanation(text: string): string {
  return dedupeSteps(text);
}
