# PLAN — Menuju 50× bersih (bukan label)

## Prinsip (dari skill planning + lean-build + investigate-first)
- Setiap claim wajib angka benchmark nyata, bukan kata "lebih baik".
- Satu bottleneck per iterasi: profile → fix → test → ukur → commit.
- Rollback kalau merusak test (bukan paksa).

## Bottleneck tersisa (diurut berdasar bukti profiling)
1. **Path.resolve() berulang** — 9.9k panggilan `_joinrealpath` (top-tottime).
   SEBELUMNYA saya rollback karena 85 test gagal, tapi investigasi menunjukkan
   85 gagal = dependensi tree-sitter hilang, BUKAN perubahan resolve cache.
   → Re-terapkan cache `path.resolve()` dengan verifikasi test yang benar.
2. **GIL contention** — `thread.lock acquire` 1.6s (34% baseline). Parallel
   extract pakai ProcessPool tapi ada lock panas di cache/stat index.
3. **Iterasi graph O(N²)** — cek di query/analyze path bila ada.

## Definisi "50× bersih"
Akumulasi gain terukur per sumbu (query, incremental, akurasi, memory, extract):
- query: 88× (terbukti)
- incremental: 53× (terbukti)
- member-call akurasi: 0→100% (terbukti)
- memory: 8.4× + time 1.4× (terbukti)
- extract speed: TARGET — cari gain dari bottleneck #1/#2

## Stop condition
- Setiap fix punya benchmark before/after.
- Suite test hijau (263 test saya + test asli).
- Tidak ada "50×" ditulis tanpa angka.
