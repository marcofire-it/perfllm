# Task 02 — `dagrunner`: esecutore parallelo di task con dipendenze

**Livello: 2 (medio)** · File da consegnare: `dagrunner.py`, `NOTES.md`

## Obiettivo

Implementare un modulo `dagrunner.py` (sola libreria standard) che esegue un insieme di task
organizzati come grafo aciclico diretto (DAG), in parallelo con thread, rispettando le dipendenze,
con retry, timeout e propagazione dei fallimenti.

## API pubblica (nomi obbligatori)

```python
class DagError(Exception): ...
class DuplicateTaskError(DagError): ...
class UnknownDependencyError(DagError): ...
class CycleError(DagError): ...

class RunResult:
    status: dict[str, str]        # nome -> "success" | "failed" | "skipped" | "cancelled"
    results: dict[str, Any]       # nome -> valore restituito (solo per i task "success")
    errors: dict[str, BaseException]  # nome -> ultima eccezione (solo per i task "failed")
    order: list[str]              # nomi dei task nell'ordine in cui sono stati AVVIATI
    attempts: dict[str, int]      # nome -> numero di esecuzioni tentate (0 se mai avviato)

    @property
    def ok(self) -> bool: ...     # True se tutti i task sono "success"

class DAG:
    def add_task(self, name: str, fn, deps=(), *, retries: int = 0, timeout: float | None = None) -> None: ...
    def topological_order(self) -> list[str]: ...
    def run(self, max_workers: int = 4, fail_fast: bool = True) -> RunResult: ...
```

## Semantica

### `add_task`
- `name`: stringa non vuota, unica. Un nome duplicato solleva `DuplicateTaskError` **subito**.
- `fn`: callable con firma `fn(deps: dict[str, Any]) -> Any`. Riceve un dizionario
  `{nome_dipendenza: risultato}` con i risultati di **tutte e sole** le sue dipendenze dirette.
- `deps`: iterabile di nomi. Le dipendenze possono essere aggiunte **prima** di essere definite
  (la validazione avviene in `run()` / `topological_order()`).
- `retries`: numero di **ritentativi** dopo il primo fallimento (`retries=2` ⇒ fino a 3 esecuzioni). Deve essere ≥ 0.
- `timeout`: secondi massimi per una singola esecuzione, `None` = nessun limite.
- Valori non validi (`name` vuoto, `retries < 0`, `timeout <= 0`, `fn` non callable) sollevano `ValueError`.

### `topological_order()`
- Solleva `UnknownDependencyError` se un task dipende da un nome non definito,
  `CycleError` se il grafo contiene un ciclo (anche un self-loop).
- Restituisce un ordine topologico **deterministico**: algoritmo di Kahn in cui, tra i task
  contemporaneamente disponibili, viene scelto sempre quello aggiunto per primo (ordine di inserimento).
- Non esegue nulla.

### `run(max_workers, fail_fast)`
- Valida il grafo come sopra **prima** di avviare qualunque task: se ci sono errori solleva l'eccezione
  e nessun `fn` deve essere stato chiamato.
- `max_workers` deve essere ≥ 1 (altrimenti `ValueError`). Non devono mai esserci più di
  `max_workers` task in esecuzione contemporanea.
- Un task viene avviato appena **tutte** le sue dipendenze sono `success` e c'è un worker libero.
  Quando più task sono pronti, vengono avviati in ordine di inserimento.
- `order` registra l'ordine di **avvio** (primo tentativo) di ogni task avviato.
- Se `fn` solleva un'eccezione viene ritentato fino a `retries` volte in più. Se fallisce anche
  l'ultimo tentativo: `status = "failed"`, `errors[name]` = ultima eccezione, `attempts[name]` = tentativi fatti.
- **Timeout**: se un'esecuzione supera `timeout` secondi va considerata fallita con un'eccezione
  `TimeoutError` (conta come un tentativo; i retry si applicano). Non è richiesto interrompere il thread,
  ma `run()` non deve attendere oltre il timeout per decidere che quel tentativo è fallito.
  Il valore eventualmente restituito da un'esecuzione scaduta va ignorato.
- **Propagazione**: ogni task che dipende (direttamente o transitivamente) da un task `failed`
  diventa `skipped` (senza mai essere avviato, `attempts = 0`).
- **`fail_fast=True`** (default): dopo il primo fallimento definitivo non vengono avviati nuovi task;
  quelli già in esecuzione vengono attesi fino al termine (o al loro timeout). I task non avviati che
  **non** dipendono dal task fallito hanno `status = "cancelled"`; quelli che ne dipendono hanno `"skipped"`.
- **`fail_fast=False`**: i task indipendenti dal fallimento continuano normalmente.
- `run()` è rieseguibile: chiamate successive sullo stesso `DAG` producono un nuovo `RunResult` indipendente.
- Un DAG vuoto restituisce un `RunResult` con dizionari vuoti e `ok == True`.
- `run()` deve terminare sempre (nessun deadlock), anche con `max_workers=1` e task che falliscono.

### Thread-safety
Il chiamante non usa `DAG` da più thread. Ma le `fn` girano in thread diversi: `RunResult` deve essere
coerente al ritorno di `run()`.

## Esempio

```python
from dagrunner import DAG

dag = DAG()
dag.add_task("fetch", lambda d: [1, 2, 3])
dag.add_task("double", lambda d: [x * 2 for x in d["fetch"]], deps=["fetch"])
dag.add_task("sum", lambda d: sum(d["double"]), deps=["double"])
dag.add_task("log", lambda d: print("fetched", d["fetch"]), deps=["fetch"])

r = dag.run(max_workers=2)
assert r.ok
assert r.results["sum"] == 12
assert r.order[0] == "fetch"
assert set(r.order[1:3]) == {"double", "log"}
```

## Vincoli

- Sola libreria standard (`threading`, `concurrent.futures`, `queue`, ecc. sono ammessi).
- Nessuna attesa attiva (busy-wait con `sleep` in loop) per la sincronizzazione.
- Il modulo non deve stampare nulla.
