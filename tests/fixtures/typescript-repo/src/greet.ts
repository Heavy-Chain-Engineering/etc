// Fixture source file. The corresponding test file greet.test.ts exists
// alongside; the F021 check-test-exists gate should allow edits to this
// file. A sibling file with no .test.ts companion is added by the test
// at runtime to verify the BLOCK path.
export function greet(name: string): string {
  return `Hello, ${name}!`;
}
