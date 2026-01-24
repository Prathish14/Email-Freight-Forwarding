## Setup

Install dependencies and run extraction + evaluation:

```bash
pip install -r requirements.txt
python3 extract.py      # Generates output.json
python3 evaluate.py     # Shows accuracy metrics
```

## Prompt Evolution

This section documents the actual prompt iteration process followed during development. Each iteration addresses concrete failure modes observed on specific emails. Accuracy numbers are indicative and were measured on a representative subset of the dataset.

### v1: Basic extraction (baseline)

- **Accuracy**: ~62%
- **Characteristics**:
  - Minimal instructions
  - No explicit port normalization rules
  - No country-only or ICD handling
  - Weak negative constraints
- **Issues observed**:
  - Port abbreviations returned as-is
  - ICD context lost
  - Ambiguous or underspecified emails not handled
  - Limited downstream resolvability
- **Concrete examples**:
  - **EMAIL_006**: Origin and destination ports returned as abbreviations ("SHA", "MAA") without expansion or ICD context, despite the email explicitly mentioning "Shanghai" and "Chennai ICD".
  - **EMAIL_039**: Origin and destination returned as codes ("PUS", "MAA") instead of full port names.
  - **EMAIL_011**: Country-only origin ("Japan") could not be resolved, resulting in null origin fields.

### v2: Rule-constrained extraction

- **Accuracy**: ~78%
- **Changes introduced**:
  - Deterministic framing
  - Strict JSON-only output
  - Explicit “do not invent” rules
  - Basic dangerous goods keyword detection
  - Generic port abbreviation expansion
- **Improvements**:
  - Hallucinations reduced
  - Output format stabilized
  - Common cases handled correctly
- **Remaining issues and regressions**:
  - Over-extraction of port phrases including country names
  - Port resolution failures when codes were not normalized
  - Dangerous goods occasionally missed
  - Country-only origins still unsupported
- **Concrete examples**:
  - **EMAIL_039**: Dangerous goods missed despite presence of a UN number (UN 2735), and origin/destination ports could not be resolved.
  - **EMAIL_014**: Origin and destination ports over-extracted as "Xingang, China" and "Chennai ICD, India", leading to downstream normalization failures.
  - **EMAIL_011**: Country-only origin ("Japan") remained unresolved, resulting in null origin fields.

### v3: Explicit business rules and edge-case handling

- **Accuracy**: ~88%
- **Changes introduced**:
  - Explicit port abbreviation expansion table
  - Enforcement of “PORT NAMES only” extraction
  - ICD inclusion rules
  - Country-only origin handling
  - Stricter dangerous goods detection via UN numbers
  - Clear separation between extraction and deterministic post-processing
- **Improvements**:
  - Port codes consistently expanded to full names
  - ICD destinations handled correctly
  - Dangerous goods reliably detected
  - Underspecified real-world emails handled without hallucination
- **Concrete examples**:
  - **EMAIL_039**: Correctly resolved port codes and names ("PUS" → "Busan", "MAA" → "Chennai"), detected dangerous goods via UN number, and accurately extracted cargo metrics across all evaluated fields.
  - **EMAIL_014**: Regression introduced in v2 resolved by enforcing “PORT NAMES only” extraction, resulting in clean values ("Xingang", "Chennai ICD").
  - **EMAIL_011**: Correctly handled country-only origin by extracting "Japan" as the origin while preserving explicit cargo volume and leaving missing fields as null.
- **Remaining limitations**:
  - Highly unstructured emails with no clear location indicators
  - Country-only mentions without sufficient context for downstream mapping

## Accuracy Metrics

Accuracy metrics were computed using the `evaluate.py` script, which compares predicted outputs against the provided ground truth on a per-field basis. All comparisons follow the evaluator’s normalization rules: case-insensitive string matching, numeric rounding to two decimals, and strict null equality.

The following field-level accuracies were observed:

- **product_line accuracy**: 100.00% (50/50)
- **origin_port_code accuracy**: 88.00% (44/50)
- **origin_port_name accuracy**: 86.00% (43/50)
- **destination_port_code accuracy**: 70.00% (35/50)
- **destination_port_name accuracy**: 70.00% (35/50)
- **incoterm accuracy**: 96.00% (48/50)
- **cargo_weight_kg accuracy**: 88.00% (44/50)
- **cargo_cbm accuracy**: 92.00% (46/50)
- **is_dangerous accuracy**: 100.00% (50/50)

**Overall accuracy**: 87.78% (395 / 450)

Lower accuracy on destination port fields is primarily due to emails where destinations were underspecified, ambiguously formatted, or mentioned only at the country or ICD level, which limits deterministic resolution.

## Edge Cases Handled

Below are key edge cases encountered during development, along with the specific problems observed and how they were addressed.

### Edge Case 1: Port codes instead of port names

- **Email ID**: EMAIL_039
- **Problem**: The email referenced ports using short codes ("PUS → MAA"). In v1 and v2, the extraction returned these codes directly, which caused downstream resolution failures and incorrect evaluation results.
- **Solution**: In v3, an explicit port abbreviation expansion table was added, and the prompt enforced extraction of port names only. This allowed deterministic resolution of both port names and port codes ("PUS" → "Busan", "MAA" → "Chennai").

### Edge Case 2: Over-extraction of port phrases with country names

- **Email ID**: EMAIL_014
- **Problem**: The email mentioned ports along with country qualifiers ("Xingang, China", "Chennai ICD, India"). In v2, stricter “extract as mentioned” rules caused the model to over-extract full phrases, leading to inconsistent port values and evaluation mismatches.
- **Solution**: In v3, the prompt was refined to explicitly require extraction of **PORT NAMES only**, while preserving ICD context where applicable. This eliminated country-level noise and restored consistent port extraction ("Xingang", "Chennai ICD").

### Edge Case 3: Country-only origin without a specific port

- **Email ID**: EMAIL_011
- **Problem**: The email referenced only a country of origin ("Japan") without specifying a port. In v1 and v2, this resulted in null origin fields, as the extraction logic assumed port-level granularity.
- **Solution**: In v3, explicit handling for country-only mentions was introduced. When no specific port is available, the country name is preserved as the origin, while downstream logic ensures missing fields remain null rather than being hallucinated.

### Edge Case 4: Dangerous goods mentioned implicitly via UN number

- **Email ID**: EMAIL_039
- **Problem**: Although the email clearly contained a UN number ("UN 2735"), v2 failed to consistently flag the shipment as dangerous goods, as detection relied on weaker keyword heuristics.
- **Solution**: v3 introduced stricter dangerous goods rules, explicitly treating UN numbers, IMDG references, and packing group information as definitive indicators. This ensured reliable DG detection without false positives.

These edge cases reflect real-world variability in freight emails and were addressed through incremental prompt refinement and deterministic post-processing, without introducing inference or hallucination.

## System Design Questions

### 1. Scale: 10,000 emails/day, 99% processed within 5 minutes, $500/month budget

At this scale, the system should be designed as an asynchronous, queue-based pipeline rather than a synchronous request–response flow. Incoming emails would be ingested into a message queue (e.g., SQS, Pub/Sub, or a lightweight Redis-backed queue), where workers consume messages independently. This decouples ingestion from processing and allows horizontal scaling based on load. Given the volume (≈7 emails/minute on average, with bursts), a small pool of stateless worker processes is sufficient.

To stay within budget, the LLM should only be used for semantic extraction, while all normalization, validation, and enrichment (port resolution, product line inference, RT handling) remain deterministic in code. Batch processing can be applied where possible, and strict timeouts with retries should be enforced to avoid stuck workers. Caching frequent ports, country mappings, and prompt templates further reduces cost and latency.

Cost control is achieved by selecting a cost-efficient model, enforcing temperature=0, limiting token usage, and avoiding reprocessing failed emails without a clear reason. With these constraints, 10,000 emails/day is feasible well under the given budget.

### 2. Monitoring: Accuracy drops from 90% to 70% over a week

Accuracy degradation should be detected through continuous evaluation against a rolling validation set or sampled ground-truth emails. A scheduled evaluation job (e.g., daily) would compute field-level and overall accuracy using the same logic as `evaluate.py`. Metrics should be tracked over time, with alerts triggered when accuracy drops beyond a defined threshold for critical fields such as port resolution or dangerous goods detection.

Once a drop is detected, the investigation starts by segmenting errors by field and by email cluster (e.g., by region, customer, or language). Comparing recent failures against previously successful cases often reveals distribution shifts, such as new port abbreviations, new email templates, or changes in how customers describe shipments. Prompt regressions are ruled out by checking prompt version hashes and deployment history.

Based on findings, corrective action may include prompt refinement, adding new deterministic rules, or updating reference data (e.g., port mappings). Any fix is validated on a holdout set before redeployment to avoid introducing new regressions.

### 3. Multilingual: 30% Mandarin, 20% Hindi emails

For multilingual inputs, the core architecture remains unchanged, but the extraction layer needs language awareness. The first step would be lightweight language detection per email. For non-English emails, either a multilingual-capable LLM is used directly, or the email is translated to English using a deterministic translation service before extraction. The latter approach keeps prompts and business rules consistent.

Domain-specific vocabulary (ports, incoterms, DG indicators) should remain language-agnostic wherever possible by relying on symbols (UN numbers, CBM, KG) and standardized terms. For language-specific cues (e.g., “危险品” for DG), additional keyword rules can be added incrementally without changing the core pipeline.

Accuracy evaluation remains unchanged: predictions are still compared against ground truth using the same field-level metrics. Multilingual samples should be explicitly included in the evaluation dataset to ensure performance parity across all languages and to detect language-specific degradation early.
