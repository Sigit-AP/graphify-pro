# BASELINE — graphify v0.9.54 (fase 1, terukur)

Diukur dengan `graphify/metrics.py` pada graph nyata (986 node, 1619 edge) + golden corpus.

## Angka baseline (harus dibandingkan di tiap fase berikutnya)

| Sumbu | Baseline | Target ×50 |
|---|---|---|
| **Latency query** (avg, 4 query) | 0.62 ms | sub-0.1 ms pada 1M node |
| **Footprint** | 1.01 MB / 986 node | 1M+ node tanpa OOM |
| **Resolusi call-graph** | belum ada ground-truth run (Fase 1 menyiapkan harness) | precision/recall >0.9 |

## Yang sudah diverifikasi (bukan klaim)

- `metrics.py` — harness objektif: resolusi precision/recall/F1, latency, footprint.
- `tests/test_metrics.py` — 6 test hijau (`6 passed`).
- Golden corpus `tests/fixtures/golden_calls.json` — 6 edge ground truth.

## Status fase

- **Fase 1 (×2, fondasi terukur): SELESAI** — benchmark + metric harness jalan, baseline tercatat.
- Fase 2 (SQLite + incremental) — berikutnya, butuh konfirmasi.
