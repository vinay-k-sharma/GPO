# Eval report — eval_20261013-184523_hybrid_n8_retrieval_ablate

## Config

```json
{
  "mode": "hybrid",
  "top_n": 8,
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
| hit@1 | 0.756 |
| hit@3 | 0.927 |
| hit@6 | 1.0 |
| hit@10 | None |
| mrr | 0.846 |
| cross_year_hit_all_docs | 0.8 |

## Per question

| id | category | first hit rank | top retrieved |
|---|---|---|---|
| fy25-q01 | numeric | 1 | 2025_annualreport:p40, 2025_annualreport:p56, 2025_annualreport:p93 |
| fy25-q02 | numeric | 1 | 2025_annualreport:p58, 2025_annualreport:p40, 2025_annualreport:p58 |
| fy25-q03 | numeric | 1 | 2025_annualreport:p18, 2025_annualreport:p41, 2025_annualreport:p6 |
| fy25-q04 | numeric | 1 | 2025_annualreport:p32, 2025_annualreport:p33, 2025_annualreport:p29 |
| fy25-q05 | numeric | 3 | 2025_annualreport:p40, 2025_annualreport:p58, 2025_annualreport:p28 |
| fy25-q06 | numeric | 1 | 2025_annualreport:p40, 2025_annualreport:p84, 2025_annualreport:p76 |
| fy25-q07 | numeric | 2 | 2025_annualreport:p59, 2025_annualreport:p24, 2025_annualreport:p90 |
| fy25-q08 | numeric | 1 | 2025_annualreport:p39, 2025_annualreport:p39, 2025_annualreport:p28 |
| fy25-q09 | numeric | 1 | 2025_annualreport:p39, 2025_annualreport:p40, 2025_annualreport:p87 |
| fy25-q10 | factual | 1 | 2025_annualreport:p65, 2025_annualreport:p40, 2025_annualreport:p67 |
| fy25-q11 | factual | 1 | 2025_annualreport:p10, 2025_annualreport:p53, 2025_annualreport:p11 |
| fy25-q12 | factual | 1 | 2025_annualreport:p12, 2025_annualreport:p51, 2025_annualreport:p6 |
| fy25-q13 | factual | 1 | 2025_annualreport:p26, 2024_annualreport:p39, 2025_annualreport:p25 |
| fy25-q14 | factual | 2 | 2025_annualreport:p20, 2025_annualreport:p20, 2025_annualreport:p19 |
| fy25-q15 | factual | 1 | 2025_annualreport:p34, 2025_annualreport:p7, 2025_annualreport:p52 |
| fy25-q16 | factual | 1 | 2025_annualreport:p3, 2025_annualreport:p6, 2025_annualreport:p10 |
| fy25-q17 | narrative | 1 | 2025_annualreport:p10, 2025_annualreport:p14, 2025_annualreport:p6 |
| fy25-q18 | narrative | 1 | 2025_annualreport:p13, 2025_annualreport:p20, 2025_annualreport:p19 |
| fy25-q19 | narrative | 1 | 2025_annualreport:p25, 2025_annualreport:p27, 2025_annualreport:p51 |
| fy25-q20 | narrative | 1 | 2025_annualreport:p14, 2025_annualreport:p14, 2025_annualreport:p26 |
| fy25-q21 | table | 1 | 2025_annualreport:p88, 2024_annualreport:p92, 2024_annualreport:p92 |
| fy25-q22 | table | 4 | 2024_annualreport:p44, 2025_annualreport:p40, 2024_annualreport:p60 |
| fy24-q01 | numeric | 2 | 2024_annualreport:p44, 2024_annualreport:p43, 2024_annualreport:p60 |
| fy24-q02 | numeric | 1 | 2024_annualreport:p62, 2024_annualreport:p44, 2024_annualreport:p44 |
| fy24-q03 | numeric | 1 | 2024_annualreport:p20, 2024_annualreport:p45, 2024_annualreport:p4 |
| fy24-q04 | numeric | 2 | 2024_annualreport:p44, 2024_annualreport:p26, 2024_annualreport:p30 |
| fy24-q05 | numeric | 1 | 2024_annualreport:p45, 2024_annualreport:p88, 2024_annualreport:p80 |
| fy24-q06 | numeric | 3 | 2024_annualreport:p44, 2024_annualreport:p28, 2024_annualreport:p43 |
| fy24-q07 | factual | 1 | 2024_annualreport:p44, 2024_annualreport:p71, 2024_annualreport:p69 |
| fy24-q08 | factual | 1 | 2024_annualreport:p12, 2024_annualreport:p12, 2024_annualreport:p4 |
| fy24-q09 | factual | 1 | 2024_annualreport:p36, 2024_annualreport:p37, 2024_annualreport:p16 |
| fy24-q10 | factual | 1 | 2024_annualreport:p12, 2024_annualreport:p12, 2024_annualreport:p14 |
| fy24-q11 | narrative | 1 | 2024_annualreport:p16, 2024_annualreport:p4, 2024_annualreport:p22 |
| fy24-q12 | narrative | 1 | 2024_annualreport:p10, 2024_annualreport:p10, 2024_annualreport:p8 |
| fy24-q13 | table | 1 | 2024_annualreport:p75, 2024_annualreport:p58, 2024_annualreport:p75 |
| fy24-q14 | table | 4 | 2024_annualreport:p44, 2024_annualreport:p60, 2024_annualreport:p90 |
| cross-q01 | cross_year | 6 | 2025_annualreport:p40, 2024_annualreport:p44, 2025_annualreport:p41 |
| cross-q02 | cross_year | 1 | 2024_annualreport:p44, 2025_annualreport:p40, 2025_annualreport:p40 |
| cross-q03 | cross_year | 3 | 2025_annualreport:p40, 2024_annualreport:p44, 2025_annualreport:p28 |
| cross-q04 | cross_year | 1 | 2025_annualreport:p32, 2024_annualreport:p36, 2024_annualreport:p36 |
| cross-q05 | cross_year | 1 | 2025_annualreport:p40, 2024_annualreport:p45, 2024_annualreport:p88 |
| na-q01 | unanswerable | None | 2025_annualreport:p10, 2025_annualreport:p40, 2025_annualreport:p20 |
| na-q02 | unanswerable | None | 2024_annualreport:p98, 2025_annualreport:p94, 2024_annualreport:p98 |
| na-q03 | unanswerable | None | 2025_annualreport:p40, 2024_annualreport:p30, 2025_annualreport:p32 |
| na-q04 | unanswerable | None | 2025_annualreport:p63, 2024_annualreport:p60, 2024_annualreport:p62 |
