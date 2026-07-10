# Evaluation harness

Regenerate + run (server must be on http://localhost:8001):

```bash
python3 eval/make_chart_dataset.py     # 20 synthetic labeled charts -> eval/charts/
python3 eval/make_tasks.py             # leak-free task files for the classification eval
# classification eval: spawn vision agents on eval/tasks/*, write eval/results/*, then:
python3 eval/score.py                  # chart type / dispersion / decision / flags / provenance
python3 eval/extraction_accuracy.py    # deterministic numeric recovery (exact landmark pixels)
python3 eval/vision_extract.py         # + agents estimate pixels -> eval/vision_extract_score.py
```
Generated PNGs/JSON and the cropped journal figures are gitignored; the scripts reproduce them.
