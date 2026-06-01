# BeverageLab Rules & Skills

This file defines the rules and skills for the BeverageLab workspace.

## 🚀 Post-Change Verification Protocol
You **MUST** run the project verification command after every code change to guarantee stability and prevent regressions.

### Rebuild and Verify Command
Run the following command from the workspace root:
```bash
docker compose run --rm web python manage.py test
```

> [!IMPORTANT]
> 1. Never skip verification before committing. The verification step **MUST** execute all unit and integration test suites.
> 2. You **MUST** update the [status.md](file:///./status.md) file after each task to reflect the current status of features, completed tasks, and architectural changes.
> 3. You **MUST** generate a git commit with an accurate, descriptive commit message representing the changes after every successful execution (only if a Git repository is initialized in the workspace; skip this step if Git is not initialized).

## 🧪 Automated Testing & Bug Prevention
To ensure that projects are robust enough to share with others, you must establish and maintain strict testing habits:

1. **Test Coverage**: Write automated unit and/or integration tests for all new features, API endpoints, and core business logic.
2. **Bug Fix Verification**: When fixing a bug, write a test case that reproduces the bug, verify that it fails, and then verify that it passes after the fix is implemented.
3. **Robust Input Validation**: Ensure tests check boundary conditions, invalid inputs, error handling paths, and API constraints to catch bugs before they reach runtime.
4. **Zero-Failure Tolerance**: All automated tests must pass successfully before a task is considered complete.

## 💎 Code Quality & Production Standards
All generated code must be clean, maintainable, and production-ready.

1. **Imports**:
   - Write all imports at the top of the file.
   - **No lazy imports** inside functions or methods unless absolutely required for dynamic loading or avoiding circular dependencies (documented with clear comments).
   - Order imports logically (standard library, third-party libraries, local imports).

2. **Types & Schemas**:
   - Add type hints to all Python function signatures, variables, and return values (or use language-appropriate typing standards).
   - Use standard data schemas (e.g. Pydantic models in Python, TypeScript interfaces in TS) for API payloads and database records.

3. **Error Handling & Logging**:
   - Do not use broad `except Exception:` blocks without logging or re-raising.
   - Use built-in logging libraries instead of raw print/console statements in production code.
   - Ensure all logs are human-readable, clear, and structured. Avoid random or cryptic words (e.g. "windy-blue-sunday-morning"). Messages should follow a simple, descriptive pattern like: `[Job/Operation] - [Category/Level] - [Detail Message]` (e.g., `Scanning - Error - Could not access directory for scanning`).

4. **Aesthetics & UI Standards**:
   - Maintain a premium visual design: consistent typography, harmonious color palettes, smooth transitions, proper margins, and descriptive spacing.
   - Do not use inline styles or raw CSS files unless explicitly requested. Always utilize the established local utility framework (like Tailwind CSS) and existing UI primitives.

5. **Framework & Architecture Decisions**:
   - When introducing new frameworks, major dependencies, or architectural shifts, present 2-3 viable options detailing the pros, cons, and trade-offs of each, and wait for user approval before executing.

6. **Modular Architecture & Code Separation**:
   - Avoid monolithic files. Keep files modular by separating logic into distinct files and sub-modules.
   - Limit file sizes (ideally under 500 lines) and function/method complexity.
   - Extend base objects or classes by importing them locally and building extensions in separate files rather than piling all behavior into a single base definition file.

7. **Security & Secrets Safety**:
   - Never hardcode private keys, database credentials, API tokens, or secrets. Always pull them from environment configurations or system environments.

8. **Environment Configurations**:
   - When introducing new variables to `.env`, immediately document them in `.env.example` with placeholders or dummy values to prevent configuration drift.

9. **No Code Stubs**:
   - Never write code stubs, temporary `TODO` comments, or truncated snippets (e.g., `// ... rest of code remains the same`). Code edits must always be fully complete and ready to run.

10. **Conventional Commits**:
    - Write git commit messages using the Conventional Commits specification (e.g., `feat:`, `fix:`, `test:`, `refactor:`, `chore:`, `docs:`) with descriptive subject lines under 50 characters.

## 💡 Token & Quota Conservation Rules
To maintain high speed and prevent burning through API limits:

1. **Diff-Only Modifications**:
   - Never overwrite a whole code file to make small edits. Always use targeted replacements (`replace_file_content` or `multi_replace_file_content` on specific line ranges) to minimize token transfer.
