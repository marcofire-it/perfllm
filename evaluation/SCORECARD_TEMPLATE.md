# Scorecard — model: `<name>` · task: `<id>` · date: <YYYY-MM-DD>

## A. Automatic tests (55)
- Tests passed: `<passed>/<total>` → core `<x/y>`, edge `<x/y>`, perf `<x/y>`
- Main failed tests and cause (max 5, one line each):
  - `<test name>`: <cause in one line>
- **A = <n>/55**

## B. Adherence to spec and instructions (15)
- Names/interfaces respected: yes/no (<detail>)
- External dependencies / forbidden constructs: none / <list>
- Delivery format (complete files, NOTES.md): ok / <problem>
- Undocumented deviations: <list or "none">
- **B = <n>/15**

## C. Code quality (15)
- Structure: <2 lines>
- Error / thread / resource handling: <2 lines>
- Strengths: <1 line>
- Weaknesses: <1 line>
- **C = <n>/15**

## D. Robustness beyond the tests (10)
| Input tried | Expected | Obtained | Outcome |
|---|---|---|---|
| <description> | <...> | <...> | ok/ko |
- **D = <n>/10**

## E. NOTES.md and own tests (5)
- NOTES.md: present/absent, quality: <1 line>
- Declared assumptions consistent with the code: yes/no
- Own tests: absent / superficial / good (<n> tests, outcome: <do they pass?>)
- **E = <n>/5**

## Total: **<A+B+C+D+E> / 100**

## Comment (5-10 lines)
<What sets this submission apart: where it understood the spec well, where it plowed ahead, which traps from
TRAPS.md it handled or missed, whether it cheated or simplified the problem, how usable it would be in
production as is.>
