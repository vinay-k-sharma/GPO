# Eval report — eval_20261013-184424_bm25_n10_retrieval_ablate

## Config

```json
{
  "mode": "bm25",
  "top_n": 10,
  "retrieval_only": true,
  "llm_model": null,
  "effort": null,
  "embed_model": "BAAI/bge-base-en-v1.5",
  "chunk_size": 400,
  "n_questions": 45
}
```

## Summary

| Metric | Value |
|---|---|
| hit@1 | 0.585 |
| hit@3 | 0.878 |
| hit@6 | 0.951 |
| hit@10 | 1.0 |
| mrr | 0.739 |
| cross_year_hit_all_docs | 1.0 |

## Per question

| id | category | first hit rank | top retrieved |
|---|---|---|---|
| fy25-q01 | numeric | 2 | 2025_annualreport:p56, 2025_annualreport:p40, 2025_annualreport:p55 |
| fy25-q02 | numeric | 1 | 2025_annualreport:p40, 2025_annualreport:p40, 2025_annualreport:p58 |
| fy25-q03 | numeric | 4 | 2025_annualreport:p94, 2025_annualreport:p95, 2025_annualreport:p85 |
| fy25-q04 | numeric | 1 | 2025_annualreport:p32, 2025_annualreport:p33, 2025_annualreport:p20 |
| fy25-q05 | numeric | 8 | 2025_annualreport:p58, 2025_annualreport:p22, 2025_annualreport:p58 |
| fy25-q06 | numeric | 1 | 2025_annualreport:p40, 2025_annualreport:p73, 2025_annualreport:p84 |
| fy25-q07 | numeric | 1 | 2025_annualreport:p24, 2025_annualreport:p59, 2025_annualreport:p88 |
| fy25-q08 | numeric | 1 | 2025_annualreport:p39, 2025_annualreport:p39, 2025_annualreport:p79 |
| fy25-q09 | numeric | 2 | 2025_annualreport:p80, 2025_annualreport:p39, 2025_annualreport:p82 |
| fy25-q10 | factual | 1 | 2025_annualreport:p39, 2025_annualreport:p67, 2025_annualreport:p65 |
| fy25-q11 | factual | 2 | 2025_annualreport:p52, 2025_annualreport:p10, 2025_annualreport:p11 |
| fy25-q12 | factual | 1 | 2025_annualreport:p12, 2025_annualreport:p11, 2025_annualreport:p50 |
| fy25-q13 | factual | 1 | 2025_annualreport:p26, 2024_annualreport:p39, 2025_annualreport:p34 |
| fy25-q14 | factual | 2 | 2025_annualreport:p20, 2025_annualreport:p6, 2025_annualreport:p20 |
| fy25-q15 | factual | 1 | 2025_annualreport:p6, 2025_annualreport:p34, 2025_annualreport:p7 |
| fy25-q16 | factual | 1 | 2025_annualreport:p3, 2025_annualreport:p5, 2025_annualreport:p5 |
| fy25-q17 | narrative | 1 | 2025_annualreport:p6, 2025_annualreport:p5, 2025_annualreport:p10 |
| fy25-q18 | narrative | 2 | 2025_annualreport:p37, 2025_annualreport:p13, 2025_annualreport:p18 |
| fy25-q19 | narrative | 1 | 2025_annualreport:p25, 2025_annualreport:p50, 2025_annualreport:p51 |
| fy25-q20 | narrative | 1 | 2025_annualreport:p14, 2025_annualreport:p26, 2025_annualreport:p46 |
| fy25-q21 | table | 2 | 2024_annualreport:p50, 2025_annualreport:p88, 2024_annualreport:p92 |
| fy25-q22 | table | 8 | 2024_annualreport:p44, 2025_annualreport:p40, 2024_annualreport:p84 |
| fy24-q01 | numeric | 2 | 2024_annualreport:p60, 2024_annualreport:p43, 2024_annualreport:p43 |
| fy24-q02 | numeric | 1 | 2024_annualreport:p44, 2024_annualreport:p43, 2024_annualreport:p44 |
| fy24-q03 | numeric | 5 | 2024_annualreport:p98, 2024_annualreport:p99, 2024_annualreport:p16 |
| fy24-q04 | numeric | 3 | 2024_annualreport:p44, 2024_annualreport:p20, 2024_annualreport:p26 |
| fy24-q05 | numeric | 1 | 2024_annualreport:p45, 2024_annualreport:p77, 2024_annualreport:p88 |
| fy24-q06 | numeric | 1 | 2024_annualreport:p43, 2024_annualreport:p28, 2024_annualreport:p44 |
| fy24-q07 | factual | 1 | 2024_annualreport:p44, 2024_annualreport:p71, 2024_annualreport:p43 |
| fy24-q08 | factual | 2 | 2024_annualreport:p28, 2024_annualreport:p12, 2024_annualreport:p4 |
| fy24-q09 | factual | 1 | 2024_annualreport:p36, 2024_annualreport:p16, 2024_annualreport:p35 |
| fy24-q10 | factual | 1 | 2024_annualreport:p12, 2024_annualreport:p12, 2024_annualreport:p14 |
| fy24-q11 | narrative | 1 | 2024_annualreport:p21, 2024_annualreport:p40, 2024_annualreport:p39 |
| fy24-q12 | narrative | 1 | 2024_annualreport:p10, 2024_annualreport:p10, 2024_annualreport:p8 |
| fy24-q13 | table | 3 | 2024_annualreport:p44, 2024_annualreport:p58, 2024_annualreport:p75 |
| fy24-q14 | table | 3 | 2024_annualreport:p60, 2024_annualreport:p44, 2024_annualreport:p76 |
| cross-q01 | cross_year | 3 | 2024_annualreport:p44, 2025_annualreport:p40, 2024_annualreport:p43 |
| cross-q02 | cross_year | 1 | 2024_annualreport:p44, 2025_annualreport:p40, 2024_annualreport:p40 |
| cross-q03 | cross_year | 4 | 2024_annualreport:p44, 2025_annualreport:p40, 2024_annualreport:p22 |
| cross-q04 | cross_year | 1 | 2024_annualreport:p36, 2025_annualreport:p32, 2024_annualreport:p36 |
| cross-q05 | cross_year | 1 | 2024_annualreport:p45, 2025_annualreport:p40, 2024_annualreport:p77 |
| na-q01 | unanswerable | None | 2025_annualreport:p18, 2025_annualreport:p18, 2025_annualreport:p18 |
| na-q02 | unanswerable | None | 2025_annualreport:p94, 2024_annualreport:p98, 2025_annualreport:p95 |
| na-q03 | unanswerable | None | 2024_annualreport:p22, 2025_annualreport:p20, 2024_annualreport:p22 |
| na-q04 | unanswerable | None | 2025_annualreport:p14, 2025_annualreport:p13, 2025_annualreport:p33 |
