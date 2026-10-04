# Tasdeeq evaluation results

- generated: 2026-10-02T20:13:59+00:00
- engines: qaari, easyocr, tesseract  |  split: eval (20 invoices)

## Setup comparison

| setup | field acc (num/date/total) | verifier acc | green precision | flag rate on wrong | corrupted recall |
|---|---|---|---|---|---|
| qaari | 35%/50%/15% | 74% | 0.545 | 0.789 | 1.0 |
| easyocr | 40%/55%/25% | 78% | 0.673 | 0.738 | 1.0 |
| tesseract | 40%/40%/0% | 93% | 0.941 | 0.987 | 1.0 |
| pipeline | 35%/50%/35% | 78% | 1.0 | 1.0 | 1.0 |

## Latency (ms)

| engine | mean | median | max |
|---|---|---|---|
| qaari | 77474.0 | 86859.9 | 196381.9 |
| easyocr | 2149.8 | 1360.1 | 17008.6 |
| tesseract | 1605.1 | 1473.6 | 2742.4 |

## Setup: qaari

| invoice | mode | invoice_no | date | total | items | overall |
|---|---|---|---|---|---|---|
| 0080 | corrupted | R✗ | G✗ | R✗ | ✗ | red |
| 0081 | mild | R✗ | G✗ | R✗ | ✗ | red |
| 0082 | clean | G✓ | G✓ | R✗ | ✗ | red |
| 0083 | corrupted | G✗ | G✓ | A✗ | ✗ | amber |
| 0084 | clean | G✓ | G✓ | R✗ | ✗ | red |
| 0085 | heavy | G✓ | G✓ | R✗ | ✗ | red |
| 0086 | clean | R✗ | R✗ | R✗ | ✗ | red |
| 0087 | heavy | G✓ | G✓ | A✓ | ✗ | amber |
| 0088 | clean | G✓ | G✗ | R✗ | ✗ | red |
| 0089 | corrupted | G✗ | G✓ | R✗ | ✗ | red |
| 0090 | clean | G✓ | R✗ | R✗ | ✗ | red |
| 0091 | mild | G✓ | G✓ | G✓ | ✗ | green |
| 0092 | mild | R✗ | G✓ | R✗ | ✗ | red |
| 0093 | mild | R✗ | G✗ | R✗ | ✗ | red |
| 0094 | clean | G✗ | G✓ | R✗ | ✗ | red |
| 0095 | mild | G✗ | G✓ | A✓ | ✗ | amber |
| 0096 | heavy | G✗ | G✗ | R✗ | ✗ | red |
| 0097 | clean | R✗ | R✗ | R✗ | ✗ | red |
| 0098 | clean | G✗ | G✗ | R✗ | ✗ | red |
| 0099 | corrupted | R✗ | G✗ | R✗ | ✗ | red |

## Setup: easyocr

| invoice | mode | invoice_no | date | total | items | overall |
|---|---|---|---|---|---|---|
| 0080 | corrupted | G✗ | G✗ | A✗ | ✗ | amber |
| 0081 | mild | G✗ | R✗ | R✗ | ✗ | red |
| 0082 | clean | G✓ | G✓ | G✓ | ✓ | green |
| 0083 | corrupted | G✓ | G✓ | R✗ | ✓ | red |
| 0084 | clean | G✓ | G✓ | G✓ | ✓ | green |
| 0085 | heavy | G✗ | R✗ | R✗ | ✓ | red |
| 0086 | clean | G✗ | G✗ | G✗ | ✗ | green |
| 0087 | heavy | G✓ | G✓ | R✗ | ✗ | red |
| 0088 | clean | G✓ | G✓ | A✓ | ✓ | amber |
| 0089 | corrupted | G✗ | G✓ | A✗ | ✗ | amber |
| 0090 | clean | G✗ | G✓ | R✗ | ✗ | red |
| 0091 | mild | G✓ | G✓ | G✓ | ✓ | green |
| 0092 | mild | R✗ | R✗ | R✗ | ✗ | red |
| 0093 | mild | G✗ | R✗ | A✗ | ✗ | red |
| 0094 | clean | G✓ | G✓ | G✓ | ✓ | green |
| 0095 | mild | G✓ | G✓ | R✗ | ✓ | red |
| 0096 | heavy | R✗ | G✗ | R✗ | ✗ | red |
| 0097 | clean | G✗ | R✗ | R✗ | ✗ | red |
| 0098 | clean | G✗ | G✓ | A✗ | ✗ | amber |
| 0099 | corrupted | G✗ | R✗ | R✗ | ✗ | red |

## Setup: tesseract

| invoice | mode | invoice_no | date | total | items | overall |
|---|---|---|---|---|---|---|
| 0080 | corrupted | R✗ | R✗ | R✗ | ✗ | red |
| 0081 | mild | R✗ | R✗ | R✗ | ✗ | red |
| 0082 | clean | G✓ | G✓ | R✗ | ✗ | red |
| 0083 | corrupted | G✓ | R✗ | A✗ | ✗ | red |
| 0084 | clean | G✓ | R✗ | R✗ | ✗ | red |
| 0085 | heavy | R✗ | R✗ | R✗ | ✗ | red |
| 0086 | clean | R✗ | R✗ | R✗ | ✗ | red |
| 0087 | heavy | G✓ | G✓ | R✗ | ✗ | red |
| 0088 | clean | R✗ | R✗ | R✗ | ✗ | red |
| 0089 | corrupted | R✗ | G✓ | A✗ | ✓ | red |
| 0090 | clean | G✓ | G✓ | R✗ | ✗ | red |
| 0091 | mild | G✓ | G✓ | R✗ | ✓ | red |
| 0092 | mild | R✗ | G✓ | A✗ | ✓ | red |
| 0093 | mild | R✗ | R✗ | R✗ | ✗ | red |
| 0094 | clean | G✓ | G✓ | R✗ | ✓ | red |
| 0095 | mild | G✓ | G✓ | R✗ | ✗ | red |
| 0096 | heavy | R✗ | R✗ | R✗ | ✗ | red |
| 0097 | clean | R✗ | R✗ | R✗ | ✗ | red |
| 0098 | clean | R✗ | R✗ | R✗ | ✗ | red |
| 0099 | corrupted | R✗ | G✗ | R✗ | ✗ | red |

## Setup: pipeline

| invoice | mode | invoice_no | date | total | items | overall |
|---|---|---|---|---|---|---|
| 0080 | corrupted | A✗ | A✗ | A✗ | ✗ | amber |
| 0081 | mild | A✗ | A✗ | R✗ | ✗ | red |
| 0082 | clean | G✓ | G✓ | A✓ | ✓ | amber |
| 0083 | corrupted | A✗ | G✓ | A✗ | ✓ | amber |
| 0084 | clean | G✓ | G✓ | A✓ | ✓ | amber |
| 0085 | heavy | A✓ | A✓ | R✗ | ✓ | red |
| 0086 | clean | A✗ | A✗ | A✗ | ✗ | amber |
| 0087 | heavy | G✓ | G✓ | A✓ | ✗ | amber |
| 0088 | clean | G✓ | A✗ | A✓ | ✓ | amber |
| 0089 | corrupted | A✗ | G✓ | A✗ | ✗ | amber |
| 0090 | clean | A✓ | R✗ | R✗ | ✗ | red |
| 0091 | mild | G✓ | G✓ | G✓ | ✓ | green |
| 0092 | mild | R✗ | A✓ | R✗ | ✗ | red |
| 0093 | mild | A✗ | A✗ | A✗ | ✗ | amber |
| 0094 | clean | A✗ | G✓ | A✓ | ✓ | amber |
| 0095 | mild | A✗ | G✓ | A✓ | ✓ | amber |
| 0096 | heavy | A✗ | A✗ | R✗ | ✗ | red |
| 0097 | clean | A✗ | R✗ | R✗ | ✗ | red |
| 0098 | clean | A✗ | A✗ | A✗ | ✗ | amber |
| 0099 | corrupted | A✗ | A✗ | R✗ | ✗ | red |
