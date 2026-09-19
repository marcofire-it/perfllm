# Scorecard — modello: `sonnet` · task: `03-minilang` · data: 2026-09-19

## A. Test automatici (55)
- Test superati: `86/86` → core `22/22`, edge `62/62`, perf `2/2`
- Test falliti principali e causa (max 5, una riga ciascuno):
  - nessuno
- **A = 55/55**

## B. Aderenza a spec e istruzioni (15)
- Nomi/interfacce rispettati: sì (`run`, eccezioni con `.line`/`.output`, CLI con exit 0/1/2, output parziale su stdout prima dell'errore)
- Dipendenze esterne / costrutti vietati: nessuna (`re`, `sys`); niente `eval`/`exec`; import senza effetti collaterali (`setrecursionlimit` solo in `run()`, ripristinato nel `finally`, righe 1142-1157)
- Formato consegna (file integrali, NOTES.md): ok (minilang.py, NOTES.md, test_minilang.py)
- Deviazioni non documentate: il lexer usa `c.isalpha()` (riga 121) e accetta identificatori non ASCII, la spec limita a `[A-Za-z_]`; `c.isdigit()` (riga 84) accetta cifre Unicode come `²` e `int()` esplode (vedi D). Tutte le altre interpretazioni (scope dei parametri unico col corpo, `break` in fn dentro while, exit 2 senza argomento) sono documentate in NOTES.md.
- **B = 14/15**

## C. Qualità del codice (15)
- Struttura: pipeline `tokenize()` → `Parser` → `Interpreter` con AST a classi e `__slots__`; `fn name` desugarato in `LetStmt(FnLit)` come dice la spec; funzioni pure di supporto (`stringify`, `ml_equals`, `trunc_div`, `trunc_mod`) facili da testare.
- Gestione errori / thread / risorse: `Env.get/set` sollevano `KeyError` convertito in `MiniRuntimeError` con la riga giusta; `RecursionError` intercettata in `run()` e convertita in `MiniRuntimeError` (riga 1152, riga 0 come fallback documentato); CLI intercetta `OSError` generico (riga 1175). Controlli di tipo con `type(x) is ...` per evitare la trappola bool/int, spiegato in NOTES.
- Punti di forza: è l'unico dei tre che non fa mai trapelare `RecursionError`; messaggi d'errore coerenti; gestione CLI la più pulita.
- Punti deboli: codice di indicizzazione duplicato tra lista e stringa (righe 1097-1108) e tra lettura e assegnamento; `ValueError` su cifre Unicode non intercettata; messaggi in italiano mescolati a identificatori inglesi.
- **C = 13/15**

## D. Robustezza oltre i test (10)
| Input provato | Atteso | Ottenuto | Esito |
|---|---|---|---|
| ricorsione profondità 1000 | ok o errore pulito | `1000` | ok |
| ricorsione profondità 3000 | ok o MiniRuntimeError | MiniRuntimeError "ricorsione troppo profonda" (riga 0) | ok |
| 501 addendi `1 + 1 + ...` su una riga | `501` | `501` | ok |
| stringa con escape `\q` | ParseError | ParseError riga 1 | ok |
| `let range = 7;` al top level | errore o shadow | MiniRuntimeError "già dichiarata" (documentato in NOTES) | ok |
| lista che contiene se stessa + `print(a)` | errore pulito o protezione | MiniRuntimeError "ricorsione troppo profonda" | ok |
| `print(1 == 1 == true)` | `true` | `true` | ok |
| sorgente con `\r\n` e tab, errore a riga 5 | riga 5 | riga 5 | ok |
| file con BOM UTF-8 | ParseError o accettato | ParseError riga 1 | ok |
| programma vuoto / soli commenti | `""` | `""` | ok |
| `fn f(a) { let a = 1; return a; } print(f(2));` | 1 o errore | MiniRuntimeError "a già dichiarata" (scelta documentata) | ok |
| cifra Unicode `²` come letterale | ParseError | `ValueError` Python grezza (riga 88) | ko |
| variabile con valore `nil` riletta e riassegnata | `nil` poi `1` | `nil` `1` | ok |
| `len()` senza argomenti | MiniRuntimeError | MiniRuntimeError riga 1 | ok |
| CLI con directory come argomento | exit 2 pulito | exit 2, nessun traceback | ok |
- **D = 8/10**

## E. NOTES.md e test propri (5)
- NOTES.md: presente, qualità: la più completa dei tre. Spiega ogni scelta non ovvia (perché `type() is`, perché uno scope unico per parametri e corpo, `break` attraverso confini di funzione) e dichiara limiti reali.
- Assunzioni dichiarate coerenti con il codice: sì, verificate una per una
- Test propri: buoni (35 test unittest, passano in 0.04 s; coprono errori parse/runtime con riga, `err.output`, closure, ricorsione 200, built-in). Mancano test CLI e performance, solo verificati a mano secondo NOTES.
- **E = 5/5**

## Totale: **95 / 100**

## Commento (5-10 righe)
La consegna più solida delle tre. Passa tutti i test nascosti, gestisce tutte le trappole della spec e, a
differenza di opus e qwen, tratta anche i confini con l'host: `RecursionError` diventa un errore MiniLang,
la CLI esce con 2 su qualsiasi `OSError`, una lista auto-referenziale non fa esplodere l'interprete con un
traceback. NOTES.md è un modello di comunicazione onesta: ogni interpretazione discutibile è dichiarata e
motivata, e corrisponde al codice. L'unica falla trovata è la cifra Unicode `²` accettata dal lexer e poi
rifiutata da `int()` di Python, un problema condiviso con opus. Il codice è leggibile con qualche duplicazione
nell'indicizzazione. Usabile in produzione per il perimetro della spec.
