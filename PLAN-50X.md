# RENCANA 50× — Graphify (Supercharged Code Intelligence)

> Status: PLANNING (belum build). Acuan: codebase nyata graphify v0.9.54 (362 file Python, ~155K baris), riset SOTA 2025–2026.

---

## 0. Baseline — apa yang graphify punya sekarang

- **Pipeline:** `detect → extract (tree-sitter AST) → build (NetworkX) → cluster (Leiden) → analyze → report → export`.
- **Ekstraksi kode:** deterministik AST, tanpa LLM. Bagus untuk gratis & lokal.
- **Penyimpanan:** `graph.json` statis (NetworkX dump). Query = BFS/traversal di memori.
- **Resolusi simbol lintas-file:** ada tapi fragmentaris per-bahasa (`symbol_resolution.py`, `pascal_resolution.py`, `ruby_resolution.py`, `csharp_dispatch.py`) + fuzzy `rapidfuzz`.
- **Kekuatan:** gratis, lokal, jujur (EXTRACTED/INFERRED/AMBIGUOUS), 20+ bahasa.
- **Kesenjangan vs SOTA (dari riset):** tidak ada LSP (type resolution lemah untuk polymorphism/method receiver), tidak ada storage queryable (SQLite), tidak ada hybrid vector+graph, benchmark retrieval tidak ada, tidak ada incremental index ber-hash.

### Definisi "×" (terukur, bukan vibes)

Setiap kelipatan diukur pada ≥1 sumbu objektif:

| Sumbu | Metrik | Baseline |
|---|---|---|
| **A. Akurasi call graph** | precision/recall resolusi simbol lintas-file (dataset berlabel) | fuzzy-only |
| **B. Kecepatan query** | latency query di graph 1M node | BFS di JSON in-memory |
| **C. Skalabilitas** | ukuran codebase max yang bisa di-index tanpa collapse | ~ratusan ribu baris |
| **D. Kualitas retrieval** | answer fidelity (jawaban benar / total) di suite soal | graph traversal polos |
| **E. Cakupan bahasa** | jumlah bahasa dengan resolusi tipe akurat | 20+ (AST), resolusi parsial |
| **F. Kebaruan** | incremental update tanpa rebuild penuh | rebuild penuh |

"50×" = akumulasi peningkatan terukur di sumbu A–F, dicapai bertahap, tiap fase punya bukti (test) sebelum naik ke fase berikutnya.

---

## FASE 1 (×2) — Fondasi terukur & benchmark

**Tujuan:** bisa mengukur, sebelum berani mengubah.

1. Bangun **benchmark retrieval suite** (10–20 soal per bahasa sampel, ground-truth label call graph).
2. Tambah **metric harness** — ukur precision/recall resolusi simbol, latency query, ukuran index.
3. Buat **golden corpus** kecil (repo sampel Python/TS/Go) dengan call-graph ground truth.
4. **Completion criteria:** suite jalan, baseline tercatat sebagai angka (bukan "terasa"). Semua test hijau.

**Bukti lolos:** `pytest` suite retrieval + metric harness menghasilkan angka baseline yang bisa dibandingkan.

---

## FASE 2 (×4) — Index SQLite & incremental

**Tujuan:** ganti `graph.json` statis → database queryable + incremental (sumbu B, C, F).

1. **Storage engine SQLite** (seperti CodeGraph/Codebase-Memory): nodes/edges/communities sebagai tabel, index terdefer.
2. **Incremental re-index** — hash konten (XXH3/blake) per file, re-parse hanya yang berubah.
3. **Query layer** di atas SQL (bukan load penuh ke RAM).
4. **Completion criteria:** query 1M-node < 100ms; re-index file tunggal tanpa rebuild penuh; benchmark menunjukkan gain terukur.

**Bukti:** benchmark latency sebelum/sesudah; test incremental (ubah 1 file → hanya 1 re-parse).

---

## FASE 3 (×8) — LSP type resolution (akurasi)

**Tujuan:** akurasi call graph level SOTA (sumbu A) — ini lompatan terbesar, sesuai riset "LSP-style resolution improves call-graph accuracy".

1. **Integrasi LSP opsional** (pyright/rust-analyzer/gopls/typescript-language-server) untuk go-to-definition presisi.
2. **Hybrid resolver:** AST cepat sebagai default; LSP untuk kasus ambigu (method receiver, pointer indirection, polymorphism, package-qualified identifier).
3. **Fallback tetap fuzzy** bila LSP tidak tersedia (tetap zero-config).
4. **Completion criteria:** precision/recall resolusi naik terukur (target: +30–50% pada kasus polymorphism vs baseline).

**Bukti:** metric harness membandingkan resolusi AST-only vs AST+LSP pada golden corpus.

---

## FASE 4 (×12) — Hybrid retrieval (vector + graph)

**Tujuan:** kualitas retrieval (sumbu D) — GraphRAG hybrid: vector narrow → graph expand → assemble.

1. **Embedding lokal opsional** (fastembed/BGE-small, seperti stakgraph) untuk semantic search — tetap lokal, tanpa cloud.
2. **Graph-aware retrieval:** dari hit vector, fan-out k-hop bidirectional (succ+pred) + interface consumer expansion (sesuai arXiv "Reliable Graph-RAG for Codebases").
3. **Community summary** untuk jawaban global (GraphRAG local search).
4. **Completion criteria:** answer fidelity naik terukur di suite soal retrieval (target: +20–40%).

**Bukti:** suite retrieval membandingkan graph-only vs hybrid.

---

## FASE 5 (×16) — Skala besar & performa

**Tujuan:** skalabilitas (sumbu C, B) untuk codebase 1M+ baris.

1. **Parallel index** (worker pool, buffer per-worker → merge → flush, seperti Codebase-Memory).
2. **Streaming/limit** — tidak load seluruh graph ke RAM untuk export/query.
3. **Optimasi cluster** untuk graph besar (Leiden incremental / sampling).
4. **Completion criteria:** index 1M baris selesai tanpa OOM; query tetap < 100ms.

**Bukti:** benchmark skala (repo besar sebagai golden corpus).

---

## FASE 6 (×20) — Cakupan bahasa & kedalaman semantik

**Tujuan:** sumbu E — resolusi tipe akurat di semua bahasa utama.

1. **Resolver per-bahasa dikonsolidasi** ke satu framework (hilangkan fragmentasi pascal/ruby/csharp/…).
2. **Edge types diperkaya** — extends/implements/injects/overrides (sesuai skema typed property graph SOTA).
3. **Completion criteria:** matrix bahasa menunjukkan resolusi tipe akurat untuk ≥ 12 bahasa.

**Bukti:** test per-bahasa (fixture + ground truth).

---

## FASE 7 (×25) — Agent-native query & MCP

**Tujuan:** graphify jadi alat yang dipanggil agent (bukan hanya CLI manusia).

1. **MCP server diperluas** — tools query yang lebih tajam (find consumers, impact analysis, shortest path typed).
2. **Structured output** untuk agent (JSON schema ketat, bukan markdown).
3. **Completion criteria:** agent (Hermes/Claude/Codex) bisa menjawab "siapa yang pakai fungsi X" dengan akurat & hemat token.

**Bukti:** e2e test agent query.

---

## FASE 8 (×32) — Diff-aware & code evolution

**Tujuan:** melacak evolusi (sumbu F lanjutan).

1. **Graph diff** antar commit — apa yang berubah, dampak (impact analysis lintas versi).
2. **Dead code / unused detection** (baseline).
3. **Completion criteria:** diff graph antar 2 commit akurat; impact analysis teruji.

**Bukti:** test graph_diff pada repo dengan riwayat.

---

## FASE 9 (×40) — Correctness & trust

**Tujuan:** kualitas mutu — jangan jadi alat yang "terlihat pintar tapi salah".

1. **Confidence calibration** — EXTRACTED/INFERRED/AMBIGUOUS diverifikasi terhadap ground truth (jangan hanya label).
2. **Self-check diagnostics** diperluas (dangling/missing/collapsed edge, dll).
3. **Fuzz testing** extractor (input aneh tidak crash).
4. **Completion criteria:** zero crash pada fuzz; confidence label ≥90% akurat vs ground truth.

**Bukti:** fuzz suite + calibration metric.

---

## FASE 10 (×50) — Polishing & final proof

**Tujuan:** menyatukan semua jadi "50×" yang terbukti.

1. **Benchmark laporan akhir** — semua sumbu A–F dibanding baseline, gain total dihitung.
2. **Dokumentasi & skill** diperbarui (graphify skill pakai fitur baru).
3. **Completion criteria:** semua test hijau, benchmark menunjukkan akumulasi ×50 terukur, dokumentasi lengkap.

**Bukti:** laporan benchmark final — angka, bukan klaim.

---

## PENILAIAN KETAT LINTAS PROFESI (sebelum build tiap fase)

Setiap fase dinilai oleh lensa berikut sebelum dianggap "matang":

| Profesi | Pertanyaan ketat |
|---|---|
| **Arsitek** | Apakah fase ini menambah kopling yang merusak "narrow core"? Apakah storage/API dirancang untuk mundur (rollback) tanpa merusak pengguna lama? |
| **Coding** | Apakah ada test sebelum code (TDD)? Apakah increment nyata dan reviewable, bukan god-module baru? |
| **Planning** | Apakah scope fase ini jelas & terpotong? Apakah kriteria selesai bisa dicek objektif? |
| **Quality** | Apakah benchmark mengukur yang benar (bukan overfit ke golden corpus)? Apakah ada test regresi? |
| **Security** | Apakah LSP/embedding/URL baru aman (trust boundary, tidak ada eksekusi asing)? |

---

## ATURAN LOOP (sesuai instruksi Anda)

1. Kerjakan **satu fase** → verifikasi (test) → nilai ketat → **baru naik ke fase berikutnya**.
2. Jika kriteria fase belum tercapai: cari sebab (apa/kenapa/bagaimana), perbaiki, uji ulang — **jangan loncat fase**.
3. Tidak ada "halu kreatif keluar konteks": setiap perubahan menelusur ke satu fase di rencana ini.
4. "Selesai" = bukti test, bukan perasaan.

---

> **Catatan jujur:** "50×" di sini didefinisikan sebagai akumulasi gain terukur di 6 sumbu objektif, dicapai bertahap. Ini target yang bisa dibuktikan — bukan klaim kosong. Fase 3 (LSP) dan Fase 4 (hybrid retrieval) adalah dua lompatan paling berdampak per riset SOTA.
