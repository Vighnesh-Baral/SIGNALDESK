# SIGNALDESK v1.1 demo script (4–5 minutes)

1. Open `/` and introduce SIGNALDESK through the scrolling product page. Explain: “SIGNALDESK turns scattered customer feedback into source-traceable product investigations.”
2. Select **Open workspace** to enter `/app`. Show the modular light workspace and its sections: Overview, Analyse feedback, Investigations, Customers, Trends & comparison, Ask SIGNALDESK, and Reports & decisions.
3. Upload the synthetic `customer_feedback_demo.csv` or use a short pasted-feedback example. Disclose that the dataset is synthetic.
4. Show source record count, Qwen3/fallback split and frequent themes. Do not equate model usage with classification accuracy.
5. Open a problem investigation card and distinguish customer-observed symptoms from unverified root-cause hypotheses.
6. Show a similarity cluster and state the method shown by the app: optional Ollama embeddings if configured, otherwise character n-gram TF-IDF wording similarity. Do not call TF-IDF fallback deep semantic understanding.
7. Show customer segmentation only if the dataset contains suitable metadata columns. Explain that rates use feedback-record denominators.
8. Show emerging-problem detection and the before/after comparison endpoint using two analysis jobs. State that prevalence changes are observational and do not prove a release caused them.
9. Ask a dataset-grounded question and show cited record IDs.
10. Show the decision pack: bug report, PRD and user-story drafts. Explain that human product/engineering review is required.
11. Download the Excel workbook and PDF research brief. Trace a quote back to its source reference.
12. If provider credentials are configured in a demo workspace, preview one Jira/Linear/GitHub/Notion item. Create it only after showing explicit approval.
13. For the competition, finish with the required real task executed inside the imported Nonilion agent. The local app/Swagger UI alone does not satisfy that demonstration requirement.

## What not to overclaim

- TF-IDF fallback is lexical similarity, not an embedding model.
- A similarity cluster does not prove a shared technical root cause.
- A triage score is a heuristic, not measured severity, ROI or revenue impact.
- Generated PRDs, bug reports and root-cause hypotheses are drafts.
- Before/after differences do not establish causation.
- The native Nonilion import is unverified until the live account accepts the request and completes an end-to-end task.
