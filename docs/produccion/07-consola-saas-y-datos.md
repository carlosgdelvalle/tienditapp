# Platform console, measurement, and data pilot

**Users:** Carlos and the Abarpay team. Merchants sign in to their store console by scanning a QR code. SaaS staff use a dedicated route and OIDC audience with Entra MFA. The operational objective is to decide which store needs help, which campaign works, which charges Finance must reconcile, and what information provides value to a supply chain without revealing its participants.

## Views the team must implement

| View / minimum role | Decision and controls | Verifiable detail |
|---|---|---|
| Operations / support | Filter by date, release, and severity; prioritize delayed bank registrations, email failures, unsynchronized registers, and pending reconciliations | Count, age, cause code, and next action. Access to a store incident with reason and audit trail; mask bank data |
| Growth / marketing | Create campaign, channel, owner, and period; record spend; distribute non-personal codes/links; measure activation and retention | Stages with distinct unique users and unique stores, conversions, denominators, unknowns, and coverage. History of the responsible owner effective on the event date |
| SaaS revenue / finance | Register a consented Control pilot, record the manual charge, receipt, currency, refund, and validity period; reconcile and identify delinquency or cancellation | SaaS charges and refunds ledger. The owner sees their terms and can cancel. A plan change preserves history and export |
| Community and partners / analyst | View the hypothesis, value to the store, interested partners, review of the simulated report, eligible cohorts, and suppression reasons | Status and cost per experiment; estimates kept separate from charges. The analyst works with aggregates. An authorized publication operator delivers only the approved version |

Create platform projections and endpoints separately from the merchant's `/api/console`. Authorize on the server according to role; hiding a button only improves presentation. Deny exports and per-store detail to marketing and analysts. Filters are retained when returning from detail. Show loading, empty, delayed-data, insufficient-access, and last successful calculation states. If an update fails, preserve the date of the previous value.

## Measurement contract

Use versioned domain events, generated on the server for durable facts. Accept a UI event only for visits, clicks, and consented interaction. Store event ID, occurrence and receipt timestamps, version, origin, environment, campaign, and a pseudonymous subject for the required unit. Separate store, person, operation, and amount indicators. Campaigns use first-party codes and an initial 28-day window from acquisition. Deduplicate by stable ID; purchases, refunds, deliveries, and confirmations reference the original fact. Do not send phone numbers, CLABE, emails, debtor names, or free-form text to analytics.

| Indicator | Source and calculation | Special cases |
|---|---|---|
| Sign-ups and new users | Unique verified identities and unique stores created in the period, as separate series | An owner with two stores counts as one person and two stores. If the invitation is not accepted, it does not count as verified sign-up |
| Activation | First completed sale per store and median time from sign-up to first sale | For cash, use a posted sale. For CoDi, use a confirmed payment. Show delay when offline cash arrives later |
| Usage and retention | Stores with a completed sale in the week / activated stores in the eligible cohort | Set time zone and observation window; mark cohorts that have not yet completed the window |
| Campaign conversion | Unique people reaching the next stage / people eligible in the previous stage; also global lead-to-payment | Deterministic acquisition through a valid code; if sources overlap without resolution, preserve an ambiguous bucket. Store first contact and later contacts without assigning two conversions |
| Control revenue | Sum of charged amounts and settled refunds in MXN cents, with cash date | Distinguish service period, collection, subscription status, and taxes. A refund does not prove cancellation |
| CAC | Campaign spend / attributable new payers, same window | Without complete spend, reliable attribution, or a positive denominator, show «Sin datos suficientes» |
| Store sales and CoDi | Amounts captured by channel, amount verified by pey, and amount pending reconciliation | Use a period, currency, and cohort of comparable transactions; show reversals/adjustments separately. Include an authorized link to the pending case |
| Supply | Item-days without stock / observed item-days; observation coverage and order-to-receipt lead time | Do not infer lost sales, savings, or causality merely from changes in the rate |
| Data-product viability | Consented participation, publishable cells, reports delivered, preparation cost, invoices charged, renewal, and benefit reported by stores | A signed agreement, issued invoice, and received payment are distinct milestones |

Use integer cents for amounts. Declare business time zone, cutoff rule, freshness, and currency in every query. In aggregated national views, set the reporting time zone and display it. A historical change to a campaign or owner preserves traceability. Demo stores, internal traffic, and SIMULADO events are excluded from real metrics by design.

## Four-reviewer rehearsal · SIMULADO

During this planning exercise, four DeepSeek agents were consulted using the same fictional 28-day snapshot. Repeat the review when data or logic changes. Deliver numbers without conclusions, ask each agent for their hypothesis, calculation, objection, and a test that could refute it, and bring them together only afterward. The integrator arbitrates units before business cards are built.

| Reviewer | Adversarial question | Resolution that must remain in the tests |
|---|---|---|
| Pro · commerce and community | Who benefits from this report, and what actually changed for the store? | Stockouts move from 15/100 = 15% to 9/70 ≈ 12.86%; coverage fell. Show both denominators and do not promise a causal improvement |
| Flash · economics | Is there collected money, and how much remains after refunds? | 7 × MXN 149 = 1,043 gross; two full refunds = 298; net collected = 745. Do not calculate profitability without costs |
| Pro · privacy | Could a buyer isolate a store, even by combining reports? | 8 of 20 invited stores accepted. Zones of 6 and 2, with one contributing 70% of a zone. Both external outputs are suppressed, including derived percentages |
| Flash · attribution | Can a winner be chosen or a value assigned to each owner? | A: 100→30→12→4; B: 40→20→14→3. Ten shared leads = 130 unique leads. Gross lead-to-payment rates are 4% and 7.5%. Show overlap and no causal winner; refunds without a channel are not assigned |

Additional test: MXN 100,000 recorded by stores, MXN 20,000 tagged CoDi, and MXN 18,000 confirmed by pey. Result: MXN 2,000 pending and 90% by **CoDi amount**. Some reviewers treated the amounts as rows or assumed the remainder was confirmed money. The verifier must fail any query that makes that cross-comparison. Three expressions of interest in Formalización and two fictional dossier requests with no recipient or charge generate MXN 0 in revenue from those products. An expression of interest creates no receivable. Count revenue only when the corresponding financial event occurs.

## Experiments and external publication

1. **Control first.** The commercial owner agrees on terms, period, and follow-up with each pilot. Use real manual charging and tenure tracking; record minutes saved with the owner and support costs.
2. **Formalización.** Interview a professional firm to validate the future scope and record store interest. This delivery does not open dossiers, perform procedures, or charge for this offer. Hypothesis: MXN 399/month for three months; includes Control, without automatic renewal. Quote the accountant separately. At expiration the store returns to Gratis unless it explicitly chooses Control. Distinguish support from the official procedure. Do not store tax documents in analytics.
3. **Dossier for a financial institution.** Later research with one entity. Hypothesis of a fixed fee paid for each dossier actually delivered. The future store would review and authorize a specific recipient; distinguish captured sales from reconciled charges. This program only records interest. Legal review precedes automation.
4. **Aggregated supply pilot.** One partner, one specific decision (for example, restocking by category and broad zone), a written purpose, validity period, recipients, and established deletion obligations. Carlos identifies the partner and reviewer; show stores the benefit and a sample before requesting optional consent. Refusal does not change Gratis or export.

### Report cycle

Record consent that is versioned and revocable per store, purpose, and scope. Design a fixed-window query over eligible stores. Require at least 10 participants per cell and individual contribution of no more than 25%. Suppress auxiliary totals, complementary cells, and successive queries that could recover values by difference. Review concentration even if the count meets the threshold. Restrict dimensions and windows to an approved catalog. Version data, rules, and the artifact fingerprint. Privacy and business owners sign the version before it is delivered through limited access with an expiration date. The ledger preserves the authorized recipient, purpose, artifact, and date. Consent withdrawal excludes new contributions and starts the agreed treatment for historical data and previous deliveries. Thresholds are initial controls and require review against the real report.

**Delivery gate:** test 9/10/11 participants, concentration just below/at/above the limit, loss of one consent between preparation and delivery, overlapping filters, and export permissions. Include one qualifying synthetic cohort, in addition to the two suppressed cohorts, to test the delivery path. Changing eligibility or recipient invalidates prior approval. Explain the permitted reason to the user without revealing the protected value. A real partner, contract, legal review, and consents are dependencies for delivering real data. [Ley de datos personales](https://www.diputados.gob.mx/LeyesBiblio/pdf/LFPDPPP.pdf) · [Ley para regular las sociedades de información crediticia](https://www.diputados.gob.mx/LeyesBiblio/pdf/LRSIC.pdf)
