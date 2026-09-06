# Loop Constraints — graphify 50x project

Active rules (enforced before every iteration):

## Push & Merge
1. Never auto-merge to main — every phase lands as reviewed, tested work.
2. One phase per iteration; no cross-phase edits in a single change.

## Paths (denylist — escalate, never edit silently)
3. Never edit `.env`, `.env.*`, or any secrets/credentials file.
4. Never edit `graphify-out/graph.json` by hand (generated artifact).

## Code
5. Run tests before claiming a phase done — no skipped assertions.
6. Minimal diff per fix: change only what the phase requires.
7. Escalate after 3 failed attempts on the same target.

## Verification (maker/checker split)
8. Every phase: implementer proposes, verifier rejects unless tests + scope pass.
9. No fabricating benchmark numbers — every metric must come from a real run.
10. "50x" is proven by measured axes A–F, never by claim.
