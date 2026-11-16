# REVIO Milestone 3 model selection

This comparison records candidate metadata checked on 15 November 2026. Candidate model-card benchmarks are not REVIO evaluation results.

| Candidate | License and language coverage | Size and local inference | Product fit and limitations |
| --- | --- | --- | --- |
| airzipm/sentiment-analysis-muril-v2 | Model card lists MIT. Explicitly English, Hindi, and Roman-script Hinglish; three labels: negative, neutral, positive. | 0.2B parameters in F32. Raw parameter storage is approximately 0.8 GB before tokenizer, framework, and runtime overhead (derived from parameter count and tensor type). Optional Transformers/PyTorch inference; weights are downloaded on first use and cached. | Selected as the optional sentiment model because it names the Hindi/Hinglish forms used by the REVIO demo. The card says Hindi/Hinglish training data is smaller, informal Roman spelling coverage varies, and the model is not evaluated on review-domain text. Its published test score is not used as a REVIO benchmark. Pinned to e3f3404276e85565d38649d5a4f35f58b1f255b7. [Model card](https://huggingface.co/airzipm/sentiment-analysis-muril-v2) |
| cardiffnlp/twitter-xlm-roberta-base-sentiment | Model card says sentiment fine-tuning covers Arabic, English, French, German, Hindi, Italian, Spanish, and Portuguese. No explicit license badge or license text is shown on the card at review time. | The repository reports 2.23 GB, including approximately 1.11 GB PyTorch and 1.11 GB TensorFlow weight files. Transformers plus a supported framework are required. | Hindi is covered, but the card does not claim Roman Hinglish support. Its training is Twitter-domain. The unclear license and duplicated framework artifacts make it a poor default for this local assessment. Revisit only after license review and a controlled comparison. [Model card](https://huggingface.co/cardiffnlp/twitter-xlm-roberta-base-sentiment), [repository files](https://huggingface.co/cardiffnlp/twitter-xlm-roberta-base-sentiment/tree/main) |

## Complaint aspects

The production default is an interpretable multilingual phrase baseline. It returns exact matched text as evidence and labels its method as rules; it is not described as a trained classifier.

An optional semantic prototype classifier uses sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2. Its model card lists Apache-2.0, 50 languages, and 384-dimensional sentence embeddings. The current inference path compares review embeddings with English, Roman-Hinglish, and Devanagari category descriptions, then keeps categories above a configured similarity threshold. It is a semantic similarity approach, not a task-trained complaint classifier; the excerpt shown alongside a semantic match is contextual evidence, not a token-level explanation. It is pinned to e8f8c211226b894fcb81acc59f3b34ba3efd5f42. [Model card](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2), [files and checkpoint sizes](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2/tree/main)

The semantic checkpoint shown in the repository is 471 MB per format, while the full repository includes multiple exported formats. It needs PyTorch and Sentence Transformers. Both this model and MuRIL are optional so application startup and the explicit deterministic fallback do not download model weights.

## Runtime behavior

- REVIO_SENTIMENT_PROVIDER=fallback (default) uses deterministic English/Hinglish/Hindi rules and marks provider as deterministic_fallback. The numeric value is rule strength, not a probability.
- REVIO_SENTIMENT_PROVIDER=transformers attempts the pinned MuRIL model lazily. A missing package, unavailable download, or inference failure falls back to the same explicitly labeled rules output. The provider must be set to transformers to request model inference.
- REVIO_ASPECT_PROVIDER=rules (default) uses the multilingual phrase baseline and exact phrase evidence.
- REVIO_ASPECT_PROVIDER=sentence-transformers requests the pinned MiniLM semantic path; load or inference failure is reported and uses the phrase baseline.
- Results are persisted by tenant, review-content hash, and versioned sentiment/aspect pipeline. Re-running the same configuration reuses saved rows. Set force=true on the analyze API to recompute them.

## REVIO evaluation

data/evaluation/indian_review_intelligence.jsonl is a separate manually labeled fictional set. Run python scripts/evaluate_intelligence.py --output ../../docs/evaluation/milestone-3-evaluation.json from services/api to measure the configured pipeline. Add --semantic only when the optional semantic checkpoint is available. The emitted metrics are scoped to that small set and local machine; they do not establish production accuracy or generalize across all Indian English/Hinglish reviews.

The 17 November 2026 local verification rerun used the deterministic fallback on the same 36 fictional labeled examples and reproduced 63.89% sentiment accuracy, 65.35% macro F1, and 88.17% macro aspect F1. Per-record fallback latency on this run was 0.044 ms median / 0.090 ms p95. These are CPU timings from the local Windows workspace, not transformer results or hosted API latency. Updated output is in `docs/evaluation/milestone-3-evaluation.json`.
