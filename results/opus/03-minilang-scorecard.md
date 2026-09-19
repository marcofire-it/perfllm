# Scorecard — modello: `opus` · task: `03-minilang` · data: 2026-09-19

## A. Test automatici (55)
- Test superati: `86/86` → core `22/22`, edge `62/62`, perf `2/2`
- Test falliti principali e causa (max 5, una riga ciascuno):
  - nessuno
- **A = 55/55**

## B. Aderenza a spec e istruzioni (15)
- Nomi/interfacce rispettati: sì (`run`, `MiniLangError.line/.output`, `ParseError`, `MiniRuntimeError`, CLI con exit 0/1/2)
- Dipendenze esterne / costrutti vietati: nessuna (solo `sys`); niente `eval`/`exec`; import senza effetti collaterali (`setrecursionlimit` solo dentro `run()`, ripristinato nel `finally`, righe 1104-1123)
- Formato consegna (file integrali, NOTES.md): ok (minilang.py, NOTES.md, test_minilang.py)
- Deviazioni non documentate: il lexer usa `c.isalpha()` (riga 123) quindi accetta identificatori non ASCII (`let è = 1;` funziona) mentre la spec limita a `[A-Za-z_]`; `c.isdigit()` (riga 79) accetta cifre Unicode come `²` e poi `int()` esplode (vedi D). CLI: argomento che è una directory → traceback Python con exit 1 invece di un'uscita pulita.
- **B = 14/15**

## C. Qualità del codice (15)
- Struttura: tre fasi nettamente separate (lexer funzione `_lex`, `Parser` a discesa ricorsiva, `_Interp`), AST con una classe per nodo e `__slots__`, sezioni commentate. Dispatch in `_exec`/`_eval` con catene di `isinstance` lunghe ma leggibili.
- Gestione errori / thread / risorse: helper `_err()` che allega sempre riga e output parziale; sentinella `_SENTINEL` per distinguere `nil` da "non dichiarato" (riga 587); segnali di controllo flusso su `BaseException` per non essere intercettati per sbaglio. `RecursionError` non viene convertita: oltre il limite trapela grezza.
- Punti di forza: distinzione bool/int sempre corretta, divisione C-style su interi arbitrari, scope del corpo separato da quello dei parametri (documentato).
- Punti deboli: `RecursionError` e `ValueError` (cifre Unicode) non intercettate; CLI gestisce solo `FileNotFoundError`.
- **C = 13/15**

## D. Robustezza oltre i test (10)
| Input provato | Atteso | Ottenuto | Esito |
|---|---|---|---|
| ricorsione profondità 1000 | ok o errore pulito | `1000` | ok |
| ricorsione profondità 3000 | ok o MiniRuntimeError | `RecursionError` Python grezza | ko |
| 501 addendi `1 + 1 + ...` su una riga | `501` | `501` | ok |
| stringa con escape `\q` | ParseError | ParseError riga 1 | ok |
| `let range = 7;` al top level | errore o shadow | MiniRuntimeError "già dichiarata" (difendibile) | ok |
| lista che contiene se stessa + `print(a)` | errore pulito o protezione | `RecursionError` grezza | ko |
| `print(1 == 1 == true)` | `true` | `true` | ok |
| sorgente con `\r\n` e tab, errore a riga 5 | riga 5 | riga 5 | ok |
| file con BOM UTF-8 | ParseError o accettato | ParseError riga 1 | ok |
| programma vuoto / soli commenti | `""` | `""` | ok |
| `fn f(a) { let a = 1; return a; } print(f(2));` | 1 o errore | `1` | ok |
| cifra Unicode `²` come letterale | ParseError | `ValueError` Python grezza (riga 83) | ko |
| variabile con valore `nil` riletta e riassegnata | `nil` poi `1` | `nil` `1` | ok |
| `len()` senza argomenti | MiniRuntimeError | MiniRuntimeError riga 1 | ok |
| CLI con directory come argomento | exit 2 pulito | traceback, exit 1 | ko |
- **D = 5/10**

## E. NOTES.md e test propri (5)
- NOTES.md: presente, qualità: ottima. Architettura, scelte (sentinella, BaseException, C-style), assunzioni esplicite e limiti reali (stima "~1500 livelli" ottimistica: 1000 ok, 3000 no).
- Assunzioni dichiarate coerenti con il codice: sì
- Test propri: buoni (104 test unittest, tutti passano in 1 s; coprono lexer, errori parse/runtime, closure, scoping, built-in, performance)
- **E = 5/5**

## Totale: **92 / 100**

## Commento (5-10 righe)
Consegna completa e precisa: passa tutti i test nascosti e gestisce tutte le trappole della spec
(divisione troncata, `if (1)` errore, `1 == "1"` false, short-circuit, re-let nello stesso scope, closure per
riferimento, riga dell'errore dentro la funzione, output parziale in `err.output`, ricorsione 200,
built-in shadowabili). Il codice è il più leggibile dei tre, con un AST tipizzato e un helper d'errore uniforme.
Il punto debole è la frontiera con Python: `RecursionError` e `ValueError` non vengono convertite in errori
MiniLang, e la CLI copre solo il caso "file inesistente". Nulla di tutto questo è richiesto dalla spec, ma un
interprete "da produzione" non dovrebbe mai far trapelare un traceback dell'host. I 104 test propri sono
i più completi tra i tre modelli. Usabile così com'è per il caso d'uso della spec.
