<!--
Thank you for contributing to VΘXΔM. The bar here is deliberate and
CI enforces all of it, so this template is a preview, not a hurdle:
better to meet the bar knowingly than to discover it check by check.
-->

## What this changes

<!--
One goal per pull request -- a branch does one thing, named for it.
Say what, and for behavior changes, cite the Standard section that
decides it (§...): every behavior in this codebase carries its
citation, and reviews argue by them.
-->

## Checklist

- [ ] **The gate passes locally**:
      `uv run ruff format --check . && uv run ruff check && uv run mypy && uv run pytest -q`
      -- coverage is 100% branch coverage, and the build fails below it.
      New code arrives with the tests that hold it there.
- [ ] **The PR title is a conventional commit** (`feat(scope): ...`,
      `fix(scope): ...`). Squash merges make the title the commit that
      lands on main, and `cz bump` derives versions from those -- the
      PR Title check holds the line.
- [ ] **Spec citations accompany behavior changes** -- in the code
      comments and docstrings, the way the surrounding code does it.
      Where the Standard is silent and reference interpreters
      (Frotz, Bocfel) settle it, the comment names the precedent.
- [ ] **If the Z-Machine itself changed** (anything under
      `src/voxam/zmachine/`): the corpus still replays -- every
      recording in `acceptance/` runs `voxam --accept` clean. The
      recordings are the interpreter's memory of every game it has
      beaten; a machine change that shifts one byte of any replay
      needs to say why.
- [ ] **`entharion/` is untouched.** It is vendored reference
      material -- the Standard, Infocom's sources, the tools of the
      elders. VΘXΔM reads it; nothing writes it.

## Loud beats wrong

If your change meets a case the Standard does not define, the house
rule is to halt loudly with a citation rather than guess quietly.
Relaxations of that rule are earned, one published-checker precedent
at a time -- if you think you have one, make the argument in the PR.
