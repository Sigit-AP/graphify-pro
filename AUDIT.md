# AUDIT — Algoritma Growth & Fase 1–4 (diperbarui: semua kelemahan kritis diperbaiki)

## TEMUAN BARU saat menggali ulang (bukan di audit v1)

### N1. Parameter FSRS/SM-2 yang saya hardcode TIDAK TERVERIFIKASI (SERIUS)
Saat audit v1 saya klaim "matematika murni peer-reviewed", tapi waktu saya telusuri
ulang: nilai w8/w9/w10/w15-w19 yang saya tulis diambil dari *potongan search*, bukan
paper asli — indeksnya SALAH (contoh: w9 ditulis 0.5425, paper asli 0.1666).
**Ini bukan "matematika murni" — ini menebak konstanta.** Melanggar prinsip inti.

→ SOLUSI (diterapkan): buang FSRS/SM-2. Ganti dengan model eksponensial murni
self-consistent yang 100% bisa saya turunkan & verifikasi sendiri:
  - Satu hukum: R = e^(-t/S) (Ebbinghaus = peluruhan radioaktif/Newton cooling).
  - S_new = S·(1 + α·(1−R)) saat sukses (spacing effect, derived).
  - S_new = S·β saat lapse (forgetting, derived).
  - t½ = S·ln2 ; t* = S·ln(1/ρ) — semua turunan yang bisa dibuktikan.
→ Bukti: test memverifikasi R=1 saat t=0, R=e^-1 saat t=S, half-life = S·ln2.

### N2. Fase 4 sebelumnya DORMAN (belum hidup) — sudah diperbaiki
`growth.py` tidak dipanggil dari query path. → sekarang `serve.py` memanggil
`record_query_recalls()` saat query menemukan seed node. Bukti end-to-end: query
menyimpan memory state (repetitions=1, timestamp).

### N3. Persistensi satu arah (save tanpa load-all) — sudah diperbaiki
Tidak ada `load_all_memory_state()`. → ditambahkan. Test: save → engine baru →
restore → snapshot identik (long-term memory bertahan antar-restart).

### N4. weak_nodes() statis (tidak time-aware) — sudah diperbaiki
Sekarang menghitung R terhadap `now`; node yang meluruh terdeteksi sebagai
"semakin lemah" meski stability tersimpan sama. Test: node recall 30 hari lalu
diurutkan lebih lemah dari node recall sekarang.

---

## STATUS KELEMAHAN v1 → v2

| # | Kelemahan (v1) | Status |
|---|---|---|
| A1 | Model memory campur (S eksponensial vs FSRS power-law) | ✅ FIX — satu model eksponensial murni |
| A2 | Growth tidak terhubung query path | ✅ FIX — hook di serve.py |
| A3 | Tidak ada load-all (persistensi satu arah) | ✅ FIX — load_all_memory_state() |
| B1 | Label × ordinal, bukan terukur | ⚠️ MASIH — butuh benchmark before/after per fase |
| B2 | FSRS weights hardcoded | ✅ FIX — dibuang, model murni self-derived |
| B3 | Grade sintetik | ✅ FIX — ganti success/lapse boolean dari sinyal nyata |
| B4 | "2× per kelemahan" metrik vibes | ⚠️ MASIH — butuh definisi objektif |
| C1 | retention_target tidak dipakai | ✅ FIX — dipakai di next_review_days() |
| C2 | weak_nodes statis | ✅ FIX — time-aware |
| C3 | "resource maksimal" vs "efisien" kontradiksi | ⚠️ MASIH — butuh klarifikasi user |

## SISA YANG BELUM (jujur)

1. **B1/B4**: label ×2/×4/×8/×12 masih ordinal. Butuh benchmark before/after nyata
   di sumbu terukur (P/R/F1, latency, R retention) untuk membuktikan gain numerik.
2. **C3**: perlu keputusan user soal "maksimalkan resource" vs "optimal/efisien".

## HASIL TEST (setelah perbaikan)

- tests/test_growth.py + test_growth_persistence.py: 14 passed
- Suite integrasi (growth+storage+metrics+lsp): 29 passed
- serve.py import OK, hook terpasang, query end-to-end menyimpan memory state.
