# Tasdeeq evaluation results

- generated: 2026-10-02T12:15:45+00:00
- engines: easyocr, tesseract  |  invoices: 20 (held-out eval split)

## Metrics

| metric | value |
|---|---|
| field accuracy — invoice_number | 50.0% |
| field accuracy — date | 70.0% |
| field accuracy — subtotal | 15.0% |
| field accuracy — tax | 30.0% |
| field accuracy — total | 20.0% |
| field accuracy — line_items_count | 35.0% |
| verifier accuracy (verdict correct) | 69.0% |
| green precision (green ⇒ correct) | 0.588 |
| flag rate on wrong fields | 0.778 |
| error recall on corrupted totals | 1.0 (4 invoices) |
| latency easyocr (mean/median/max ms) | 32117.4/31161.8/48922.9 |
| latency tesseract (mean/median/max ms) | 1857.0/1845.3/3005.4 |

## Per-invoice verdicts

| invoice | mode | invoice_no | date | total | items ok | overall |
|---|---|---|---|---|---|---|
| 0080 | corrupted | R✗ | A✗ | A✗ | ✗ | red |
| 0081 | mild | A✗ | R✗ | R✗ | ✗ | red |
| 0082 | clean | A✓ | G✓ | A✓ | ✓ | amber |
| 0083 | corrupted | A✓ | G✓ | R✗ | ✗ | red |
| 0084 | clean | G✓ | G✓ | R✗ | ✓ | red |
| 0085 | heavy | A✗ | R✗ | R✗ | ✓ | red |
| 0086 | clean | R✗ | A✗ | R✗ | ✗ | red |
| 0087 | heavy | G✓ | G✓ | R✗ | ✗ | red |
| 0088 | clean | G✓ | G✓ | A✓ | ✓ | amber |
| 0089 | corrupted | A✗ | G✓ | A✗ | ✗ | amber |
| 0090 | clean | A✓ | G✓ | R✗ | ✗ | red |
| 0091 | mild | G✓ | A✓ | A✓ | ✓ | amber |
| 0092 | mild | R✗ | A✓ | R✗ | ✓ | red |
| 0093 | mild | R✗ | A✓ | R✗ | ✗ | red |
| 0094 | clean | A✓ | G✓ | A✓ | ✗ | amber |
| 0095 | mild | G✓ | G✓ | R✗ | ✓ | red |
| 0096 | heavy | R✗ | A✗ | R✗ | ✗ | red |
| 0097 | clean | R✗ | A✗ | R✗ | ✗ | red |
| 0098 | clean | R✗ | A✓ | R✗ | ✗ | red |
| 0099 | corrupted | A✓ | A✓ | R✗ | ✗ | red |
