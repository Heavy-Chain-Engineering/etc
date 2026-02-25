# Abstraction Rules

## Status: MANDATORY
## Applies to: Architect, Backend Developer, Code Reviewer

## Core Rules

1. **Twice Before Abstracting.** A pattern must appear at least twice before creating an abstraction. Three similar lines of code is better than a premature abstraction.

2. **YAGNI.** Don't build for hypothetical future requirements. Build for the current task. Refactor when the future arrives.

3. **Every Abstraction Has a Cost.** An abstraction adds a level of indirection. It must earn its keep by reducing cognitive load or preventing errors. If it doesn't, delete it.

4. **Name It or Inline It.** If you can't give an abstraction a clear, descriptive name that adds understanding, it shouldn't exist.

## What to Abstract
- Shared business rules (validation, calculation) used in 2+ places
- External service interfaces (wrap behind a protocol for testability)
- Complex algorithms that benefit from a descriptive name

## What NOT to Abstract
- One-time operations (just write the code inline)
- Configuration (use simple constants or environment variables)
- "Just in case" wrappers around libraries
- Thin delegating methods that add no value
