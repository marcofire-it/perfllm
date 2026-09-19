# submissions/

One folder per model, one subfolder per task, with the files exactly as the TASK.md requires:

```
submissions/
├── opus/
│   ├── 01-logstats/
│   │   ├── logstats.py
│   │   ├── NOTES.md
│   │   ├── test_logstats.py        (optional, written by the model)
│   │   └── raw_response.md         (raw chat reply, when the model had no file access)
│   ├── 02-dagrunner/dagrunner.py ...
│   └── 03-minilang/minilang.py ...
└── sonnet/
    └── ...
```

Rules:
- The model folder name is free (use name + version, e.g. `claude-opus-5`, `gpt-5-mini`, `qwen3-coder`).
  No spaces. Folders starting with `_` are ignored by `--all`.
- Copy the files **exactly as produced by the model**, with no corrections. If the model replied with
  `=== FILE: ... ===` blocks, extract each block into its file (see `evaluation/split_response.py`).
- To evaluate the same model more than once (different temperature, "second chance"), use suffixes:
  `gpt-5__run2`.
- Keep the raw reply as `raw_response.md` in the task folder: it is needed for section B of the rubric
  (format, complete files) and to see whether the model asked questions instead of delivering.

Round-1 contents (`opus`, `sonnet`, `qwen`) are published untouched, for transparency.
