// Fixture test file. Presence allows edits to ../greet.ts per F021
// check-test-exists. The body doesn't need to be a runnable test —
// the F021 gate only checks for file existence + naming pattern.
import { greet } from "./greet";

test("greet returns a greeting", () => {
  expect(greet("world")).toBe("Hello, world!");
});
