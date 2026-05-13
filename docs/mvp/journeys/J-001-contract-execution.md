---
journey_id: J-001
title: Counsel executes a contract
actor: Counsel
actor_role: Legal counsel on the contracting team
trigger: |
  A sales rep emails: "We need a contract drafted for the new customer."
outcome: |
  Counter-signed PDF stored in the CRM, linked to the opportunity,
  with key terms (price, term length, parties) populated as structured fields.
status: locked
captured_at: 2026-05-13T10:00:00Z
captured_by: Engineer (J. Vertrees) + SME (anonymized)
sources: [interview]
---

# J-001 — Counsel executes a contract

## Actor

Counsel works on the contracting team. Their job is contract execution:
receiving sales requests, drafting agreements from templates, negotiating
terms with customers, and recording executed contracts in the CRM. They
care about: not making mistakes (audit risk), not being the bottleneck
(sales is impatient), and not doing the same data-entry work twice.

## Trigger

A sales rep sends an email with deal details — customer name, deal size,
term length, special terms — and asks for a contract draft. Usually 1-5
of these per day, varying complexity. Volume spikes at end of quarter.

## Outcome

A counter-signed PDF stored in the CRM, linked to the right opportunity,
with the key terms (price, term length, parties, jurisdiction) extracted
into structured fields so reporting and renewals can find them.

## Steps

1. Sales rep email lands in Counsel's inbox.
2. Counsel opens the deal in the CRM, reviews the terms requested.
3. Counsel picks a contract template from the shared template library.
4. Counsel fills variables: party names, dollar amount, term length, jurisdiction.
5. Counsel sends the draft back to Sales for internal redline.
6. Sales emails the customer; customer redlines the draft.
7. Counsel reconciles redlines, sends a final version.
8. Customer e-signs via the e-sign tool.
9. Counsel counter-signs.
10. Counsel uploads the executed PDF to the CRM and populates the
    structured term fields by hand.

## Failure modes

- **Wrong template picked.** The library has 20+ templates; picking the
  wrong one means the contract has the wrong terms. Often discovered
  AFTER signature, which is expensive to fix.
- **Variables filled inconsistently.** Free-form variable entry across
  Word documents means audit-time the same customer might have three
  different name spellings or two different dollar amounts.
- **E-sign envelope expires.** If the customer doesn't sign within the
  envelope's TTL, the whole signature flow restarts.
- **Counter-signature missed.** Customer signs, but Counsel forgets to
  counter-sign. The contract is "in execution" but not actually
  executed. Status reporting wrong.
- **CRM fields not populated.** Manual data-entry after signature is
  tedious; gets skipped under time pressure. Reporting wrong; renewals
  miss critical dates.

## Tools / Systems touched

- **CRM** (lead/opportunity/account records, structured term fields)
- **Word** (template editing, variable fill)
- **Shared drive** (template library)
- **E-sign tool** (envelope creation, signature flow)
- **Email** (sales requests, redline exchange, internal handoffs)

## Emotional journey

- **Steps 1-3:** Confident, routine. Counsel knows the template library
  cold.
- **Steps 4-5:** Focused. Variable-fill is detail-heavy and mistakes are
  costly. Counsel double-checks every dollar amount.
- **Steps 6-7:** Anxious if redlines are aggressive. Counsel has to
  judge what's negotiable and what's not, often without bandwidth to
  ask senior counsel.
- **Steps 8-9:** Relief once the signature comes in. The hard part is
  done.
- **Step 10:** Tedious. "I'm doing this work twice — I already filled
  these variables, and now I'm typing them into the CRM by hand."
  Often skipped or rushed.

## Open questions

- Are template variables versioned? What happens to in-flight contracts
  when a template changes?
- Who owns the redline workflow when Counsel is out of office?
- How are escalations to senior counsel triggered? Currently informal —
  Counsel emails. Is there a process?
- Could the structured term fields be populated from the same variables
  Counsel filled in Word, eliminating step 10?

## Notes for product

This journey was captured to demonstrate the journey-shape capture
pattern. The actor name has been abstracted; the workflow is real but
not tied to any specific HCE customer.

Three platform gaps this journey surfaces that no prior PRD addressed:

1. **Template management.** Counsel picks templates by hand from a
   shared drive. No template-version awareness, no variable taxonomy.
2. **Document automation.** Variables filled in Word, then re-typed
   into the CRM. Same data, two manual entries.
3. **E-sign integration.** Envelope status not visible to Sales or
   Counsel in one place; expiration handling is manual.

These three platform categories are the intersection any contract-
execution MVP must include. Without this journey captured, a PRD pile
focused on CRM features or e-sign features individually would miss the
fact that ALL THREE need to work for ONE customer to complete a
contract.
