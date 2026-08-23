# Sentiment baseline data

`train.csv` and `golden.csv` are a small, hand-curated, bilingual (Turkish/English)
bootstrap dataset -- **not production training data**. They exist so the baseline model,
its evaluation report and the regression test in `tests/evaluation/` are reproducible
without depending on a real, licensed corpus of customer reviews.

- `train.csv` (70 rows) trains `voxera.ml.sentiment.model.SentimentBaselineModel`.
- `golden.csv` (24 rows, disjoint from `train.csv`) is the held-out set used for the
  evaluation report and the golden-dataset regression test (see docs/ROADMAP.md
  Phase 4 and the project spec's "Golden Dataset" section).

Replacing these with real, human-labeled review data (ideally thousands of rows per
language, sampled across products/sources) is expected before this model is trusted in
production -- see `docs/ROADMAP.md`.
