# PRD: Knowledge Graph POC for Domain-Heavy Regulated Projects

**Status:** Proof of Concept (standalone project, outside `etc` harness)
**Author:** Jason Vertrees
**Date:** 2026-04-17
**Expected duration:** 1 weekend for POC + 1 week for formal comparison writeup

## Purpose

Validate the hypothesis that a **property graph knowledge graph**, built from
a client project's primary source material and curated by humans, gives agents
materially better working context than file injection alone.

If validated, this graduates into a production pattern for `etc`:
`docs/sources/` manifest, an indexer tier (FTS + KG), freshness hooks, and
standards integration. If *not* validated, we've spent a weekend and learned
that file injection is sufficient at the scales we care about — a useful
negative result.

## Why now

Three active client projects share the same shape:

1. **VenLink** — DDD-structured multi-tenant SaaS, 1M+ LOC Salesforce exports,
   regulatory PDFs (EWS InfoSec Questionnaire, GDPR references), interview
   transcripts, meeting recordings, ADRs
2. **Novasterilis** — regulated medical/sterilization industry, already running
   Apache Jena Fuseki (RDF triple store), multiple data-loading scripts
3. **Covr.care** — greenfield regulated domain, will accumulate the same
   source-material-to-code trail as VenLink has today

VenLink's April 2026 audit surfaced 10 code quality findings. At least three
had a root cause that a property graph KG would have made trivially detectable:

1. **Tenant isolation broken** — `org_id` meant different things in different
   bounded contexts. Review missed it because cross-context semantic drift is
   invisible to single-file analysis.
2. **STATUS_MAP never validated** — the ETL declared mappings for values that
   never appeared in the actual Salesforce data. Pure code-to-reality mismatch.
3. **Decision provenance fragmented** — "why is this code like this?" required
   grepping ADRs, meeting transcripts, regulatory PDFs, and commit messages
   separately.

Each of these problems maps to a distinct KG retrieval pattern (pattern-
matching, graph-diff, path-traversal). The POC is designed to validate all
three in a single, narrow experiment.

## The hypothesis (the one thing the POC is proving)

> For realistic engineering tasks in domain-heavy regulated projects, an agent
> equipped with a property-graph query tool produces output that is
> (a) more accurate, (b) more complete with respect to domain/regulatory
> constraints, and (c) uses less total context than the same agent equipped
> only with file injection.

The experimental design (section "The Experiment" below) operationalizes each
of a/b/c into measurable criteria.

## Success criteria

The POC is **successful** if all of these hold:

1. **Measurable context reduction** — For the chosen comparison task, the
   graph-equipped agent uses ≤ 10KB of graph-derived context compared to
   ≥ 30KB of file injection for equivalent task coverage.
2. **Qualitative output delta** — Either (a) the graph-equipped agent
   references at least one domain relationship that the file-injection agent
   misses, or (b) a blind human evaluator rates the graph-equipped output as
   more accurate.
3. **Rebuild-equivalence** — Build the graph, capture a canonical query
   result. Delete `.index/`. Rebuild from the same manifest + sources +
   curation. Run the same query. Results must be byte-identical (or identical
   under a deterministic canonicalization). Non-determinism in the extractors
   is a blocker, not a footnote.
4. **Staleness detection works** — Modify a source file. Run `--verify`.
   It must report the mismatch. Run the agent against the stale graph. The
   circuit breaker must engage and either hard-block or fall back (see Design
   Decisions D3).
5. **Graph freshness feasibility** — The indexer can re-index one modified
   source file in < 30 seconds. Freshness at edit-time must be feasible; if
   incremental rebuild takes minutes, the `.meta`-style auto-reconciliation
   pattern won't work in production.

The POC is a **red flag** if any of these hold:

- Graph schema requires more than 10 node types to capture the chosen
  bounded context — indicates schema explosion and future maintenance burden
- Agent cannot formulate useful Cypher without heavy query-proxy
  scaffolding — indicates the query-ergonomics story is weaker than expected
- Ingest of the 10-50MB corpus takes more than 10 minutes — indicates
  bootstrap cost is prohibitive
- Rebuild-equivalence fails (same inputs → different graph) — indicates
  non-deterministic extractors that would erode trust in production

## Scope

### In scope

- **Locked: VenLink Relationships bounded context.** Chosen because the
  April 2026 VenLink audit produced a documented answer key: three known
  bugs (tenant isolation, STATUS_MAP mismatch, decision provenance
  fragmentation) whose detectability by the KG is pre-specified. The POC
  can verify "did the graph catch finding #5?" directly rather than
  relying on subjective output quality. Source material lives at
  `~/clients/venlink/src/venlink-platform/`; the POC implementer copies a
  redacted slice into `docs/sources/` (see Edge Cases on PII redaction).
- **10–50 MB of real source material** covering at least 3 types:
  - At least one regulatory PDF
  - At least one structured export (CSV, JSON, or SQL dump)
  - Internal docs (DOMAIN.md, ADRs, interview transcripts)
  - Code (the target bounded context's source tree)
- **`docs/sources/` structure** with MANIFEST.md and CURATION.md
- **One graph database** selected via web research against the criteria in
  Technical Constraints
- **Deterministic indexer** that reads MANIFEST.md + CURATION.md + sources
  and produces the graph
- **One query tool** exposed to a test agent (direct Python function for POC;
  MCP server is the production path)
- **One task comparison** — the same realistic engineering task run twice,
  once with file injection, once with graph queries. Outputs captured,
  deltas measured.
- **Verify + circuit-breaker** — `build-graph.py --verify` implementation
  and a hard-block circuit breaker when the graph is stale (see D3)

### Out of scope

- Production infrastructure (no Docker orchestration, no Kubernetes, no
  managed services, no persistence beyond an embedded DB file or single
  Docker container)
- Freshness hooks integrated with `etc` (the POC measures feasibility,
  not integration)
- Multi-project support
- Semantic search / embeddings (pure graph query only — embeddings are a
  separate axis that can layer on later)
- Query-proxy agents (the POC should show whether the agent can handle
  Cypher directly; if it can't, that is itself a finding)
- Anything in client projects other than the chosen one
- FTS indexer (mentioned below as the cheap first indexer for the eventual
  `etc` integration — not part of the POC)

## The `docs/sources/` pattern (scaffolded by the POC)

Even though the POC is standalone, it establishes the source-material
pattern that will become an `etc` v1.8 standard. The POC repo SHOULD have:

```
docs/sources/
  README.md                     # Explains the pattern
  MANIFEST.md                   # Source registry (authored by humans,
                                #   parsed by machines — same shape as
                                #   INVARIANTS.md / SEAMS.md / CONCEPT-NNN)
  CURATION.md                   # Human-asserted facts/corrections (CUR-NNN)
  regulatory/                   # Public standards, compliance PDFs
  interviews/                   # Stakeholder transcripts, meeting notes
  exports/                      # Data dumps (Salesforce, SQL, platform JSON)
  docs/                         # Prior BRDs, SRDs, whitepapers
  code/                         # Reference/legacy code (copies or submodules)
  media/                        # Screenshots, diagrams, audio/video
  .index/                       # Derived artifacts (gitignored)
    graph.db                    # The compiled KG
    graph.metadata.json         # Build provenance for staleness detection
    extraction-cache/           # Cached deterministic extractor outputs
```

### MANIFEST.md entry format

One entry per source, level-2 heading. Required fields: ID, Path, Category,
Format, Received, Received from, Confidentiality, Content hash. Optional:
Supersedes, Extracted, Indexed by, freeform prose.

```markdown
## SRC-001: EU GDPR Article 17 — Right to Erasure

Primary regulatory source for data-deletion compliance. Cited by CONCEPT-012
(data retention) and SEAM-003 (user-deletion flow).

- **Path:** regulatory/eu-gdpr-art-17-2024-03.pdf
- **Category:** regulatory
- **Format:** pdf
- **Received:** 2026-04-01
- **Received from:** Client-provided (Emma Chen, Legal)
- **Confidentiality:** public
- **Supersedes:** SRC-045 (prior 2018 version)
- **Content hash:** sha256:a7b3...
- **Extracted:** text, citations
- **Indexed by:** fts, graph
```

### Confidentiality tiers

| Tier | Example | In git? |
|---|---|---|
| public | Published regulatory PDFs, industry standards | Yes |
| internal | BRDs, interview transcripts, meeting notes | Project-level decision |
| restricted | Salesforce exports with PII, signed NDAs, creds | Never (external storage, MANIFEST.md references path) |

The MANIFEST.md entry is always committed, regardless of tier. The
*existence and metadata* of a source is always version-controlled even when
the raw file is not. This matters for audit trails.

### CURATION.md entry format

Human-asserted facts, corrections, or provenance annotations that the
extractors can't infer from source material. Overlaid on top of the
auto-extracted graph as the final build step.

```markdown
## CUR-001: CONCEPT-001 implementation lives in VendorSearchService

- **Subject:** CONCEPT-001
- **Predicate:** IMPLEMENTED_BY
- **Object:** src/venlink/search/search_service.py:47
- **Type:** additive | override | provenance
- **Confidence:** high | medium | low
- **Asserted by:** Jason Vertrees
- **Asserted at:** 2026-04-17
- **Rationale:** Verified during VenLink audit 2026-04-16 (finding #5)
- **Overrides:** None (or a CUR-NNN / edge identifier to supersede)
```

**Critical invariant:** CURATE writes always go to CURATION.md — never
directly to the graph. A full rebuild from MANIFEST.md + CURATION.md +
sources must produce an identical graph.

## Technical constraints

### Graph database: pick via web research against these criteria

The POC implementer MUST begin with a **30-minute web research pass** to
select the graph database. The landscape of embeddable graph databases
changes rapidly (Kuzu was archived in late 2025; the Neo4j embedded mode
was removed). Do not trust older PRDs, blog posts, or LLM knowledge for
the specific choice — verify current state.

**Non-negotiable criteria:**

1. **Paradigm: property graph (labeled property graph / LPG)** — not
   RDF/SPARQL. See "Why property graph, not RDF" below. If the best-fit
   tool is RDF-only, escalate back to the PRD author before proceeding.
2. **Embeddable OR runnable in a single Docker container** — no managed-
   service dependency. The POC must run on a laptop offline.
3. **Python bindings** — either a native driver or an HTTP client library.
   No JVM-only drivers.
4. **Cypher query language** (or openCypher / GQL) — because agent-
   generated queries are a core hypothesis of this POC. If the tool only
   supports Gremlin, SPARQL, or a proprietary DSL, it fails the criteria.
5. **Actively maintained** — last commit < 90 days, no archival notices,
   no "we've pivoted to SaaS" signals. Check GitHub pulse, not the
   marketing site.
6. **Permissive license** — Apache 2.0, MIT, BSD, MPL 2.0. No AGPL or
   source-available.

**Soft preferences:**
- Single-process / single-file storage > Docker-required
- Fast bulk import (tens of thousands of nodes/sec)
- Visualization support (built-in or community)

**Candidates to evaluate (starting point — verify current state):**

| Candidate | Paradigm | Embedded? | Query Lang |
|---|---|---|---|
| Neo4j Community | LPG | Docker only (embedded removed) | Cypher |
| Memgraph | LPG | Docker | Cypher |
| FalkorDB | LPG | Redis module (Docker) | Cypher |
| Apache AGE | LPG | Postgres extension | Cypher |
| NebulaGraph | LPG | Docker (multi-component) | nGQL |

**Decision deliverable:** write `experiments/graph-db-adr.md` (a
lightweight ADR) documenting: tool selected, alternatives considered, why
it won, fallback if issues arise. Required before the indexer is built.

**Fallback if nothing cleanly fits:** Neo4j Community in a Docker
container. Cypher reference implementation, richest ecosystem, highest
LLM-friendliness. Don't spend more than a day fighting for purely-
embedded.

### Why property graph, not RDF

For agent-facing queries, **Cypher is dramatically easier for LLMs to
write correctly than SPARQL**. This is the first-order concern for this
POC.

Secondary reasons:
- DDD entities have edge properties naturally ("relationship *started on*
  2024-03-15"). RDF requires reification.
- Closed-world assumption fits application data.
- Rich ecosystem and visualization.

RDF would be the right call only if the domain required semantic-web
interop (HL7 FHIR, FIBO), OWL inference, or federated queries across
independent knowledge bases. None of VenLink / Novasterilis / Covr have
those requirements as primitives. If one develops one later, the
port-to-RDF cost is manageable (schema work, not data migration).

### Schema: keep it small

Target 5–7 node types, 5–10 edge types. If the domain requires more, note
it as a finding — the POC stops at 10 types total. Example schema for
VenLink Relationships:

```
Node types:
  - Organization          (id, name, type, status)
  - User                  (id, email, role)
  - Document              (id, title, type, path)
  - Concept               (id, name, definition)
  - RegulatoryRequirement (id, citation, requirement_text)
  - CodeFile              (id, path, bounded_context)
  - Decision              (id, title, date, adr_path)

Edge types:
  - MEMBER_OF             (User -> Organization)
  - RELATIONSHIP_WITH     (Organization -> Organization)
  - DEFINED_IN            (Concept -> Document)
  - CITES                 (Document -> RegulatoryRequirement)
  - IMPLEMENTS            (CodeFile -> Concept)
  - MOTIVATED_BY          (Decision -> Document)
  - IMPLEMENTED_BY        (Decision -> CodeFile)
```

### Node ID determinism (required for rebuild-equivalence)

Node IDs MUST be content-addressed, not UUIDs. Specifically:

```python
node_id = sha256(
    entity_type + ":" + source_ref + ":" + canonical_identifier
).hexdigest()[:16]
```

Example: `sha256("Organization:SRC-045:ORG-12847").hexdigest()[:16]`.

This ensures the same input (MANIFEST + CURATION + sources) always
produces the same graph, regardless of machine or build order. Non-
determinism anywhere in the pipeline is a bug — not a "flaky test" to
retry.

### Extractor determinism (required for rebuild-equivalence)

All extractors must be deterministic. For extractors that use LLMs (e.g.,
entity extraction from unstructured prose), the extractor MUST cache its
output in `.index/extraction-cache/` keyed by content hash. Rebuild
replays the cache. Only unseen content hits the LLM.

Cache format:
```
.index/extraction-cache/
  <content_hash>.json
```

Cache entry:
```json
{
  "content_hash": "sha256:...",
  "extractor_version": "v1",
  "extractor_model": "claude-haiku-4-5",
  "extracted_at": "2026-04-17T14:23:11Z",
  "entities": [...],
  "edges": [...]
}
```

The `extractor_version` field is bumped when extraction logic changes —
rebuilds then correctly invalidate old cache entries.

## The build CLI

`scripts/build-graph.py` supports three modes:

### `--rebuild` (CREATE)

Full clean build. Delete `.index/graph.db`, rebuild from scratch.

```
$ python3 scripts/build-graph.py --rebuild
  Deleting .index/graph.db ...
  Reading MANIFEST.md ....... 47 sources
  Reading CURATION.md ....... 12 human-asserted edges
  Extracting from sources:
    regulatory/ .............. 203 nodes, 412 edges
    interviews/ .............. 18 nodes, 34 edges
    exports/ ................. 6,429 nodes, 12,847 edges
    docs/ .................... 89 nodes, 156 edges
    code/ .................... 412 nodes, 1,203 edges
  Applying curation overlay:  12 edges added, 3 auto-edges corrected
  Writing .index/graph.db
  Writing .index/graph.metadata.json
  Build complete. 7,151 nodes, 14,652 edges in 42 seconds.
```

### `--update` / no args (UPDATE)

Incremental rebuild based on hash comparison. Default mode.

```
$ python3 scripts/build-graph.py
  Loading .index/graph.metadata.json ...
  Comparing hashes:
    manifest:   unchanged
    curation:   changed (CUR-013 added)
    sources:    SRC-042 changed, SRC-089 superseded by SRC-090
  Changed nodes to recompute: 47
  Curation overlay changes: +1 edge
  Removing orphaned nodes from superseded SRC-089 ...
  Applying changes ...
  Build complete. 7,152 nodes, 14,653 edges in 3 seconds.
```

### `--verify`

Compare current state to `.index/graph.metadata.json`. Report
mismatches without rebuilding. Exit non-zero on any drift.

```
$ python3 scripts/build-graph.py --verify
  Comparing graph.metadata.json to current state:
    manifest_hash:    MATCH
    curation_hash:    MATCH
    source_hashes:    41 of 47 MATCH
                      SRC-042: MISMATCH (file changed after build)
                      SRC-089: MISSING (referenced but not on disk)
  Graph is STALE.
  Exit: 1
```

## The query tool

Expose as a Python function for the POC (MCP comes later in `etc`
integration):

```python
def graph_query(cypher: str) -> list[dict]:
    """Run a read-only Cypher query against the current graph.

    Raises GraphStaleError if build-graph.py --verify would fail.
    Returns list of result rows as dicts.
    """
```

The `GraphStaleError` is the circuit breaker from Design Decision D3.
When raised, the agent must fall back to file injection and surface a
warning that the graph needs rebuilding.

## Staleness defenses (layered)

1. **Staleness metadata** — every query result includes `graph_built_at`
   and `graph_schema_version`. Agent checks freshness before trusting.
2. **Content-hash verification** — `--verify` catches silent drift in
   ~2 seconds regardless of graph size.
3. **Provenance-aware queries** — every edge carries `source_ref`,
   `extraction_method`, `confidence`, optional `superseded_by`. Agents
   can filter by provenance: prefer `human_curation` > `ast_parse` >
   `regex` > `llm_extract`.
4. **Circuit breaker** — `graph_query()` raises `GraphStaleError` if the
   graph is stale. Hard fail, not silent degrade.

## Design decisions (locked)

- **D1 — Source material in git:** Public tier committed, internal
  project-level, restricted never (external storage referenced by
  MANIFEST.md path). Rationale: matches how engineering teams actually
  work; manifest metadata is always versioned regardless of raw material.
- **D2 — Manifest format:** Markdown (same pattern as INVARIANTS.md,
  SEAMS.md, CONCEPT-NNN). Compiled `.index/manifest.json` gives
  indexers machine-readable form.
- **D3 — Staleness circuit breaker:** Hard block for v1 (agent refuses
  the task, tells user to rebuild). Soft fallback (`C — background
  rebuild + retry`) deferred to production version. Rationale: hard
  block forces trust in graph freshness; soft fallback hides the
  problem. Once rebuild reliability is proven, promote to C.
- **D4 — Cross-source relationships:** Both. Manifest captures explicit
  human-curated relationships (supersedes, cites-as-primary, derived-
  from). Graph indexer adds discovered relationships as separate edge
  type (`mentions`). Agent filters by edge type for curated-only vs.
  all.

## Module structure

```
{poc-project}/
  README.md                            # What this POC proves, how to run
  indexer/
    __init__.py
    ingest_pdfs.py                     # Regulatory PDFs → Document + RegulatoryRequirement nodes
    ingest_exports.py                  # CSV/JSON → Organization + User nodes
    ingest_markdown.py                 # .md files → Concept nodes
    ingest_code.py                     # Python ast → IMPLEMENTS edges
    build_graph.py                     # Main entry point (--rebuild / --update / --verify)
    extraction_cache.py                # Content-hash-keyed extractor cache
  query/
    __init__.py
    graph_tool.py                      # graph_query() + GraphStaleError
  experiments/
    scope.md                           # Which bounded context was chosen and why
    graph-db-adr.md                    # Graph DB selection ADR
    task_description.md                # The engineering task being compared
    baseline_file_injection.md         # File-injection agent output
    experimental_graph_query.md        # Graph-query agent output
    comparison.md                      # Measured deltas, findings, recommendation
    rebuild_equivalence_proof.md       # Shows identical query results before/after rebuild
  docs/sources/
    README.md                          # Pattern explanation
    MANIFEST.md                        # SRC-NNN entries
    CURATION.md                        # CUR-NNN entries
    regulatory/                        # Real regulatory PDFs (redact PII)
    interviews/                        # Real transcripts (redact PII)
    exports/                           # Real structured exports (redact PII)
    docs/                              # Real docs (DOMAIN.md, ADRs)
    code/                              # Copy of target bounded context
    .index/                            # (gitignored)
      graph.db
      graph.metadata.json
      extraction-cache/
  tests/
    test_determinism.py                # Rebuild produces identical graphs
    test_verify.py                     # --verify detects all drift modes
    test_circuit_breaker.py            # GraphStaleError raised correctly
    test_extractors.py                 # Each extractor produces expected counts
    test_query_tool.py                 # Representative queries return expected shapes
  scripts/
    build-graph.py                     # Thin CLI wrapper over indexer/build_graph.py
```

## The experiment

### Step 1: pick the task

The task must be:
- **Realistic** — something an engineer would actually do
- **Cross-cutting** — touches at least 2 entity types and references at
  least 1 regulatory requirement
- **Bounded** — completable in one agent turn (~20 minutes)

Because the bounded context is locked to VenLink Relationships, the
task candidates are pre-selected and each maps to one of the three
retrieval patterns the POC is stress-testing. Pick the one that best
fits the implementer's schedule; document the choice in
`experiments/scope.md`.

**Task A — Pattern-matching query (validates detection of tenant isolation drift):**

> "Refactor the `org_id` filter in VendorProfile search to respect the
> tenant isolation concept. Before writing code, query the graph for
> every filter clause across IAM, Relationships, Search, and Compliance
> that uses `org_id`, identify any that diverge from the canonical
> pattern (`filter == current_user.org_id`), and propose fixes."

Success condition: the graph-equipped agent flags the
`vendor_profile.org_id` filter as divergent from the pattern used in
the other three contexts. The file-injection agent does not (or takes
substantially more reading to get there).

**Task B — Graph-diff query (validates STATUS_MAP-style mismatch detection):**

> "Validate the STATUS_MAP in the Relationships ETL against the actual
> Salesforce export. Identify any declared mappings that reference
> status values never appearing in the real data, and any status values
> in the data that have no declared mapping."

Success condition: the graph-equipped agent produces the symmetric
difference directly via a single query. The file-injection agent must
reconstruct the comparison manually by reading the CSV and the Python
dict, and is more likely to miss values.

**Task C — Path-traversal query (validates decision provenance retrieval):**

> "Document the decision provenance for the `recipient_resolver` pattern
> in `invitation_service.py`. Trace from the code file back through the
> ADRs that motivate it, the meeting transcripts that informed the
> ADRs, and any regulatory citations that justify it."

Success condition: the graph-equipped agent returns a complete
provenance trail with typed edges in one query. The file-injection
agent has to grep ADRs, transcripts, and regulations separately and
often finds broken links (an ADR that doesn't cite its transcript, a
commit that doesn't reference an ADR).

### Step 2: run it twice

**Baseline:** file injection + `requires_reading` for all relevant
standards, docs, and code files. Capture: total context tokens, agent
output verbatim, any mistakes.

**Experimental:** same task, same agent, but with `graph_query` tool
available. Instruct the agent to *query the graph first* for relevant
entities, concepts, and regulatory citations before writing code.
Capture: total context tokens (graph results + any file reads), agent
output verbatim, any mistakes, Cypher queries the agent generated.

### Step 3: measure

| Metric | Baseline | Experimental | Delta |
|---|---|---|---|
| Total context tokens | | | |
| Files read | | | |
| Graph queries made | 0 | | n/a |
| Regulatory citations referenced | | | |
| Domain concepts referenced correctly | | | |
| Domain concepts referenced incorrectly | | | |
| Missed constraints (found by reviewer) | | | |
| Time to completion | | | |

### Step 4: write findings

`experiments/comparison.md` captures:

- Quantitative deltas from the table
- Qualitative observations (did the agent use the graph well? struggle
  with Cypher? get irrelevant results?)
- Schema findings (did 5–7 node types suffice? what was missing?)
- Indexing cost (time, LLM tokens if any)
- Freshness feasibility (re-index one modified file, measure time)
- Rebuild-equivalence proof results
- Recommendation: graduate to `etc` primitive, keep as plugin, or
  abandon

## Edge cases

1. **Redaction** — primary source material often contains PII, trade
   secrets, or regulatory-restricted data. Redact before committing to
   the POC repo. Real regulatory PDFs and Salesforce exports often do.
2. **PDF extraction is lossy** — regulatory PDFs are often tables with
   multi-column layouts that `pdfplumber` mangles. If extraction quality
   is the bottleneck, note as a finding and move on; don't over-invest
   in PDF parsing.
3. **Schema mismatch** — source material may not fit the 5–7 node
   schema cleanly. That's a finding, not a failure. Document where it
   didn't fit.
4. **Agent can't write Cypher** — if the test agent struggles to
   formulate queries, try a query-proxy prompt ("here's the schema,
   translate this intent to Cypher"). If even that fails, that's a major
   finding — POC recommendation becomes "KG needs query-proxy layer"
   rather than "KG is ready."
5. **Rebuild-equivalence fails** — if the same inputs produce different
   graphs across rebuilds, track down the non-determinism (unstable
   extractor output? ordering issue? UUIDs instead of content hashes?)
   before declaring POC results valid. A non-deterministic KG cannot be
   trusted in production.
6. **Extraction cache invalidation** — if extractor logic changes mid-
   POC, bump `extractor_version` and force re-extraction. Otherwise
   you'll debug bugs-that-aren't-bugs because old cached outputs don't
   match new extractor logic.
7. **Source material > 50MB** — if the chosen bounded context's real
   source material exceeds 50MB, subsample deterministically (first N
   rows of the export, first K pages of each PDF) and document the
   sampling strategy in `experiments/scope.md`.
8. **VenLink source material redaction workflow** — the VenLink repo at
   `~/clients/venlink/src/venlink-platform/` contains real vendor PII
   in Salesforce exports (`marks-comments-full.json`,
   `marks-comments-raw.json`, `responses.txt`) and potentially in
   meeting transcripts. Before copying into the POC's `docs/sources/`,
   run a redaction pass: replace emails with `[REDACTED_EMAIL_{hash}]`
   preserving uniqueness, replace names with `[REDACTED_NAME_{hash}]`,
   scrub SSNs / phone numbers / API keys entirely. The POC must never
   commit un-redacted material to a public-adjacent repo, even
   transiently.

## Security considerations

- **PII redaction before commit.** Primary source material often has
  PII (names, emails, SSNs in Salesforce exports), trade secrets
  (unpublished business logic in interview transcripts), or regulated
  data. Do not commit raw source files with sensitive content.
- **Graph file is derived from sensitive material** — the compiled
  `graph.db` may contain indexed forms of PII. Gitignore it.
- **Credentials never in sources** — if a source contains API keys,
  DB passwords, etc., it must be in the `restricted` tier (external
  storage) and the MANIFEST.md entry must not include the sensitive
  content.
- **Query tool bind to localhost** — if using MCP server, bind to
  localhost only.
- **Don't share POC artifacts externally** — graph files, experimental
  outputs, and MANIFEST.md entries naming real stakeholders are
  internal artifacts. Redact before sharing outside the team.
- **Extraction cache contains source content** — the cache stores
  extracted entities and edges from source material. Gitignore
  `.index/extraction-cache/` and treat it as the same confidentiality
  tier as the highest-confidentiality source it contains.

## Research notes — starting points

Not required reading but useful for the implementer:

- **Graph DB landscape (April 2026):** the embedded-graph space
  contracted in 2025. Kuzu was archived. Neo4j removed embedded mode.
  Current pragmatic choices for POC work are Neo4j in Docker or
  Memgraph in Docker. Revisit in 6 months.
- **Cypher reference:** https://neo4j.com/docs/cypher-manual/current/ —
  applicable to Memgraph, FalkorDB, Apache AGE, Neo4j.
- **openCypher standard:** https://opencypher.org — cross-vendor subset.
- **DDD + graph modeling:** Martin Fowler's work on domain model
  patterns maps well to graph schemas.
- **Existing `INVARIANTS.md` parser:** `hooks/check-invariants.sh` —
  regex for `## CONCEPT-NNN:` and `**Verify:**` is directly reusable
  in the markdown indexer for MANIFEST.md and CURATION.md.
- **Novasterilis existing Fuseki setup:** `load_rdfs.py` in their repo
  shows they're already loading RDFs. If POC validates and
  Novasterilis adopts, consider whether to maintain two backends (LPG
  for most clients, RDF for Novasterilis) or migrate them to a
  unified LPG.
- **VenLink audit findings** (memory/lessons-nc-integration-gaps.md,
  session history 2026-04-16) — the three examples that motivated
  this PRD (tenant isolation, STATUS_MAP, decision provenance). Use
  these to pick the POC task.

## Relationship to `etc`

This POC is deliberately *outside* the `etc` harness. If validated:

1. The source-material pattern graduates to an `etc` v1.8 standard
   (`standards/process/source-material.md`), with `init-project`
   scaffolding `docs/sources/` on every new project.
2. A `/collect-sources` skill helps with intake workflow (categorize
   new material, generate MANIFEST.md entries, check confidentiality).
3. A `check-sources.sh` hook enforces manifest-required on any write
   to `docs/sources/` (same pattern as `check-required-reading.sh`
   inverted).
4. The FTS indexer ships first (SQLite FTS5, cheapest value delivery)
   as `scripts/index-sources.py`. Graph indexer is the follow-on.
5. The query tool becomes an MCP server (`kg-mcp`) that `etc`'s
   `inject-standards.sh` can invoke as an additional context source.
6. `CONCEPT-NNN` entries in `INVARIANTS.md` become graph nodes
   automatically — the verify commands become graph traversals.
7. `requires_reading` gains a sibling field `requires_graph_subgraph`
   with a Cypher query the agent runs before editing.

If not validated: we have a spec for the source-material pattern
(still useful even without the graph layer), and a documented reason
not to invest further in KGs at current project scales.

## What the implementer SHOULD NOT do

- Skip the web research pass for graph DB selection
- Use UUIDs for node IDs (breaks rebuild-equivalence)
- Call an LLM without caching its output (breaks determinism)
- Commit any source material marked `restricted`
- Add CURATE edits directly to the graph (breaks rebuild-equivalence)
- Skip the `--verify` implementation (circuit breaker depends on it)
- Invest more than 30 minutes in PDF parsing quality (out of scope)
- Build an FTS indexer (not part of this POC)
- Build embeddings / RAG (not part of this POC)
- Build query-proxy scaffolding until it's proven the agent needs it
