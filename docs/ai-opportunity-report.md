# REVIO AI Opportunity Report

**Assessment status:** Demonstration product, not a production service. This report uses the available REVIO implementation and its committed fictional evaluation sets. No real customer data, live review-source connection, hosted LLM call, or deployment was used. It covers the AI opportunity and evidence categories specified in the current Cynbit submission request; a separate assessment rubric was not provided.

## Opportunity

Indian consumer businesses receive feedback across locations, review platforms, and languages. A manager may need to identify refund or payment complaints, spot an unusual increase at one location, find the relevant policy, and prepare a careful response. REVIO brings those tasks into one review-operations workspace: review triage, location analytics, unconfirmed crisis signals, policy retrieval, and human-reviewed response drafting.

The intended opportunity is to help a person prioritize and prepare work. REVIO does not claim quantified time savings, revenue uplift, improved ratings, or reduced churn; there is no deployed customer cohort or outcome study supporting those claims.

## Implemented AI-assisted workflow

1. **Review understanding:** Store sentiment, heuristic language/script, complaint categories with text evidence, urgency rationale, and recommended action. Deterministic rules are the default; optional MuRIL sentiment and multilingual semantic aspect modes exist.
2. **Crisis monitoring:** Surface explainable, unconfirmed patterns from stored review analyses. A signal is not a verified incident.
3. **Knowledge retrieval:** Embed Indian English, Hindi, and Hinglish questions with pinned multilingual E5 and retrieve tenant-filtered passages from uploaded business policies. Results include sources; the search abstains when no passage meets its configured threshold.
4. **Response preparation:** A LangGraph StateGraph loads and analyzes one review, retrieves evidence, drafts a language-matched reply, checks selected factuality risks, and saves a versioned draft with its workflow trace and citations.
5. **Human decision:** A reviewer edits, approves for internal use, or rejects the draft. The audit trail records transitions. Approval does not publish or send a response.

The default response is a clearly labeled deterministic demo template. A configurable OpenAI-compatible provider is available but was not called during this assessment. No credentials are included in source control. Review text and retrieved policy content would be sent to the selected provider if hosted mode were configured.

## Evaluation evidence

### Sentiment and complaint categories

The local deterministic fallback was measured on a separate, manually labeled set of 36 fictional examples: overall accuracy **63.89%** and macro F1 **65.35%**. Group accuracy was 83.33% for Indian English (12 examples), 75.00% for Roman Hinglish (8), 50.00% for Hindi Devanagari (8), and 37.50% for mixed scripts (8). The fallback has weak negative recall (**46.67%**) and should be treated as a triage aid, not a reliable multilingual classifier.

The optional pinned MuRIL model reached 66.67% accuracy and 59.69% macro F1 on the same 36 examples; neutral recall was 16.67%. It did not outperform the fallback on macro F1, so it is not the default. The interpretable aspect baseline reached 87.88% micro F1 and 88.17% macro category F1 on this small set, but cleanliness recall was 28.57%. All metrics are single-annotator development measurements, not production guarantees.

### Retrieval

Pinned `intfloat/multilingual-e5-small` was measured on 30 known-relevance questions plus 6 no-match questions over six fictional policy documents. It achieved Recall@1/3/5 of **53.33% / 80.00% / 100.00%**, MRR **0.7061**, thresholded Recall@5 **93.33%**, and abstained on all 6 no-match queries with 0 false positives. The selected threshold was tuned on the same set and is not independently calibrated. On the measured Windows CPU environment, warmed query embedding plus vector retrieval was **25.19 ms median / 32.54 ms p95**; model load process RSS was **648.07 MB** and model snapshot disk size was **470.44 MB**.

The retrieval results are useful for comparing the two local candidates in this curated dataset. They do not establish broad Hindi/Hinglish coverage, factual policy correctness, or cloud-host performance. Full per-query metrics and methodology are in [`knowledge-retrieval-report.md`](knowledge-retrieval-report.md) and [`data/evaluation/knowledge_retrieval_results.json`](../data/evaluation/knowledge_retrieval_results.json).

### Response generation

The response workflow's quality has not been benchmarked. The live M5 run used the deterministic fallback, and the hosted provider path was exercised only by a mocked API test. No token, hosted inference latency, or response-quality result is claimed. The workflow test verifies graph completion, tenant-scoped citations, edit/approve history, and selected guardrail behavior; these are functional checks, not a measure of customer-response quality.

## Guardrails and limitations

- The 45 review examples and six policy documents are fictional and labeled `DEMO / SYNTHETIC DATA`.
- Review text and policy passages are untrusted input. Prompt-injection phrase flags are heuristic advisories, not comprehensive protection.
- Response checks look for selected unsupported amounts, timelines, and commitments. They are not semantic factuality verification. A cited passage may be outdated, inapplicable, or wrong.
- Missing or low-relevance evidence leads to a cautious draft that avoids policy promises; a human must still verify the wording and evidence.
- High/critical cases are marked for human escalation; REVIO does not actually notify an escalation team.
- The `X-Tenant-Slug` header is not identity verification or authorization. The public demo must not be used with real reviews or private business policy.
- No live integrations to Google, Zomato, Swiggy, or other review sources are connected; no response is posted externally.

## Cost and operating proposal

The local evaluation made no hosted AI calls, so hosted model inference charges for those evaluation runs were $0.00. Local compute, electricity, storage, and bandwidth are not priced. Response-provider costs remain unknown because no provider, model account, or live traffic profile was configured.

No hosting resources have been created, so current deployment spend is $0. The proposed Vercel Hobby plus personal GitHub Codespaces route can use $0 of additional spend only while the owner's included free quotas remain available and the assessment use qualifies for Vercel Hobby's personal, non-commercial terms. GitHub Free personal accounts list 120 Codespaces core-hours and 15 GB-month storage; a 4-core Codespace consumes four core-hours for each running hour. Account balance and actual service use have not been verified. Do not add a payment method, start a paid trial, or claim a guaranteed free public SLA. Details and provider sources are in deployment.md.

## Scaling path

The prepared assessment topology is intentionally single-instance and disk-backed. It prioritizes working demonstration and durable local SQLite/vector state. It has no HA, queue, authentication, rate limit, or multi-instance coordination. For production, first add authenticated tenant membership and abuse controls; move SQL records to managed PostgreSQL, uploaded content to object storage, and vectors to a server-backed vector store; then add durable queued processing, monitored backups, calibrated evaluations, and representative human-reviewed language data. Keep model versioning and measured rollback behavior for any classifier change.

## Reproducibility

- Sentiment/aspect evaluation: `services/api/scripts/evaluate_intelligence.py` with the committed 36-example dataset.
- Retrieval model evaluation: `services/api/scripts/evaluate_knowledge.py --model both` with the committed multilingual set and pinned model revisions.
- Full recorded results: `docs/evaluation/`, `data/evaluation/knowledge_retrieval_results.json`, and the M3/M4 sections of [`technical-report.md`](technical-report.md).
- The deterministic response template has functional tests, but there is no response benchmark or independent quality score to reproduce.
