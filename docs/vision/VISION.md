# Industrialized System Synthesis

**Status:** Research / Vision  
**Owner:** Jason Vertrees  
**Collaborator:** Jim Snyder (Chief Architect, CS Disco)  
**Started:** 2026-02-24  
**Version:** 2

---

## One-Liner

A declarative, ontology-grounded system specification that acts as a living control plane — queryable by humans, executable by agent swarms, and continuously reconciled against running systems.

---

## The Thesis

Software systems have a biological parallel that goes deeper than metaphor:

| Biology | System Synthesis |
|---|---|
| DNA (genotype) | Declarative system spec |
| Gene expression machinery | Agent swarm — spun up to reconcile state, not permanent residents |
| Cells | Components/services — interfaces hiding implementation, encapsulated, specialized |
| Cell communication (receptors, signaling) | Structured APIs, message contracts, event schemas |
| Organism (phenotype) | Running system |
| Natural selection | Tests, observability, user feedback |
| Homeostasis | Continuous convergence to desired state |

**Critical distinction:** Cells are NOT agents. Cells are the **components** of the running system — services with interfaces hiding implementation, communicating via structured protocols. Agents are the **gene expression machinery** — they come into existence in response to a spec delta, do their work (write code, modify services, update infra), and the system converges. Agents are the *process*, not the *architecture*.

The insight: **build the software development process itself as a biological system.**

The spec is not documentation. It is the control plane. Change the spec, agents reconcile the system. Query the spec, get semantically grounded answers. The system converges continuously — not through batch deployments, but through declarative reconciliation.

---

## Core Capabilities

### 1. Declarative Reconciliation (like k8s)

The spec IS the desired state. Change the spec, the system converges.

- Spec diffs are detected automatically
- Deltas decompose into work units
- Agent swarms fan out — greenfield and brownfield in the same pass
- New services, code modifications, test updates, infra changes — all from a single spec mutation
- GitOps for the *entire system*, not just infrastructure
- Infrastructure as Code (Terraform, Pulumi, CloudFormation, Ansible, k8s) was the first partial genotype — but it stopped at infrastructure. Business logic, domain semantics, data flows, auth patterns, service interactions, API contracts — all still phenotype

### 2. Semantic Queryability

The spec is a knowledge graph you can interrogate:

- "When I hit localhost:8080, how does the auth flow work?"
- Returns: text description + interaction diagrams (mermaid) + component ownership + trace paths
- All answers are **semantically grounded** in the spec, not probabilistically guessed from code
- Deterministic semantics, not LLM inference

### 3. Federated Spec Topology

A top-level manifest references constituent sources:

```
system.spec (top-level manifest)
├── references: repo://auth-service
├── references: repo://billing-service
├── references: infra://k8s-cluster
├── references: schema://user-events
└── ontology: domain.md (grounded semantics)
```

- Like UV workspaces, Terraform root modules, or k8s Kustomize overlays
- Each source exposes its own local spec
- Top-level composes them and resolves cross-cutting concerns
- The "organism" spec is a composition of "organ" specs

---

## The Notation Problem

Natural language specs are too ambiguous. Code is too implementation-bound. We need something in between — but "in between" is more nuanced than it first appears.

### Naive Assumption: The Notation Must Be Unambiguous

Terence Tao's properties of good notation (from thesephist's "Notational Intelligence"):
- **Unambiguity** — every expression has unique interpretation
- **Expressiveness** — every domain idea is representable
- **Suggestiveness** — similar concepts have similar-shaped expressions
- **Natural transformation** — natural domain operations correspond to natural symbol manipulations

These are necessary at the *execution layer*. But academic research on communication systems reveals a deeper truth.

### The Ambiguity Gradient

Piantadosi et al. (2012) prove mathematically that **all efficient communication systems will be ambiguous**, assuming context is informative about meaning. Zipf's Law (1949) establishes that frequently used concepts get compressed, naturally creating ambiguity. Koçak et al. (2022) show that ambiguity can actually **compensate** for semantic differences in human-AI communication.

This means the spec notation should not be uniformly precise. It should operate on an **ambiguity gradient**:

- **Architecture depth** — strategically ambiguous, natural-language-like. "Auth service handles OAuth2 login." Different stakeholders read this differently and that's OK.
- **Contract depth** — semi-formal. Interfaces, schemas, interaction patterns. Precise enough for validation, flexible enough for multiple implementations.
- **Execution depth** — formally precise, machine-executable. Unambiguous instructions that agents act on.

This mirrors how DNA works: the same gene expresses differently depending on tissue, environment, and regulatory context. The "ambiguity" is resolved by context, not eliminated by precision.

### The Spec as Boundary Object

Star & Griesemer (1989) define **boundary objects** as artifacts that are "adaptable to different viewpoints and robust enough to maintain identity across them." The system spec must be exactly this:

- **Product person** reads it and sees capabilities and user flows
- **Engineer** reads it and sees contracts, dependencies, and technical constraints
- **Ops** reads it and sees deployment topology and scaling requirements
- **Agent** reads it and sees executable work units with formal preconditions

Same artifact, different lenses. Identity maintained across viewpoints.

This is the core research question: **What does this notation look like?**

### Requirements (Refined)

1. **Formally precise at execution depth** — machines need unambiguous instructions
2. **Strategically ambiguous at communication depth** — humans across roles need shared understanding without forced agreement on implementation details
3. **Context-resolving** — the same spec element means different things at different zoom levels, and the notation supports that
4. **A boundary object** — adaptable to product, engineering, ops, and business viewpoints while maintaining structural identity
5. **Computable** — not just readable, but executable and queryable
6. **Ontology-grounded** — deterministic semantics at the foundation

### Candidate Approaches & Influences

- **LinkML** — schema language used by OntoGPT for ontology-grounded extraction. Outputs JSON, YAML, RDF, OWL. Designed for semantic interoperability.
- **Wolfram Language** — symbolic manipulation, computable notation that can represent formulas, functions, and abstract concepts natively.
- **K8s YAML + CRDs** — proven declarative desired-state model with reconciliation loops. The UX pattern to emulate.
- **Mermaid / PlantUML** — diagram-as-code for queryable visual output.
- **OntoGPT / SPIRES** — zero-shot extraction of structured knowledge from text using ontologies. Bridge from existing docs/code to formal specs.
- **domain.md** — Jason's existing pattern for grounding AI agents in business context. The seed of the semantic foundation layer.

---

## Brownfield Adoption Path

The system must be adoptable incrementally. You can't ask someone to spec their entire system on day one.

### Identifying Declared State vs. Existing State

A **system state extractor** builds a representation of the running system in the same notation as the spec:

- **Code-level:** AST parsing, dependency graphs, API route extraction, schema introspection (ts-morph, Swagger/OpenAPI, database schema dumps)
- **Infra-level:** Terraform state, k8s API, cloud provider APIs (this part is largely solved)
- **Runtime-level:** OpenTelemetry traces, API gateway logs, service mesh topology — the system tells you how it actually behaves
- **Semantic-level:** OntoGPT-style extraction — take existing code + docs + traces and extract structured representation grounded in domain ontology

The output is a **derived spec** — "here's what we think the system currently is, expressed in the same notation as the desired spec."

### Diffing

Once declared state and derived state are in the same notation, diffing becomes graph comparison:

- **Structural diffs:** "spec says auth-service exposes /login, derived state shows no such endpoint"
- **Semantic diffs:** "spec says auth uses OAuth2 with PKCE, derived state shows basic API key auth"
- **Topological diffs:** "spec says billing-service talks to auth-service, derived state shows it talks directly to the user DB"

The diff produces **reconciliation work units** — typed, scoped, prioritized deltas that agents pick up.

### Incremental Adoption Phases

**Phase 0 — Observe only.** Extract the derived spec from the existing system. No declared spec yet. Just show people: "here's what your system actually is." This alone is valuable — most teams don't have this. **THIS IS THE TROJAN HORSE.**

**Phase 1 — Spec a slice.** Pick one bounded context (e.g., auth). Write the declared spec for just that slice. Diff against derived state. Surface the gaps. No agents yet — just visibility.

**Phase 2 — Reconcile a slice.** Same bounded context, but now agents propose changes to close the gaps. Human approval required. "AI writes code, but AI does not ship code."

**Phase 3 — Expand.** More slices adopt declared specs. The top-level federated manifest grows. Cross-cutting queries start working ("how does auth flow across services?").

**Phase 4 — Continuous.** Spec changes trigger agent swarms automatically. CI/CD is replaced by continuous reconciliation. The spec IS the deployment pipeline.

---

## Key Design Principles

1. **Semantics as the floor, not the ceiling.** The spec resolves meaning before anything else runs.
2. **Declarative, not imperative.** Describe what, not how. Agents figure out how.
3. **Federated, not monolithic.** Specs compose like organisms compose from organs.
4. **Continuously reconciled.** Not batch-deployed. The system converges.
5. **Queryable.** The spec is a knowledge graph, not a document.
6. **Agent-native.** Designed for machine execution, not just human reading.
7. **Strategically ambiguous.** Precise where machines need precision, flexible where humans need room.
8. **Boundary object.** Same artifact serves product, engineering, ops, and agents — different lenses, shared identity.

---

## Intellectual Lineage

### Jason's Prior Work

- **"Nature's Code: How Life Informs Tech"** (LinkedIn) — Full taxonomy: structured communication, encapsulation, specialization, redundancy, feedback loops, genotype/phenotype parallel. The foundational essay.
  - https://www.linkedin.com/pulse/natures-code-how-life-informs-tech-jason-vertrees-xbj2c
- **"Evolution as Product Management"** (Heavy Chain blog) — Gene pool as roadmap, mutation as feature branch, natural selection as analytics. The feedback loop that closes the system.
  - https://jvertrees.hashnode.dev/evolution-as-product-management
- **"The Tyranny of State Space"** (Heavy Chain blog) — Boltzmann/protein folding as energy landscapes that guide convergence. Software lacks this. Specs-as-energy-landscapes could provide it.
  - https://jvertrees.hashnode.dev/the-tyranny-of-state-space
- **"The Most Important File in Your Repository is domain.md"** (Heavy Chain blog) — Semantic grounding as foundation, not afterthought. The practical precursor to ontology-grounded specs.
  - https://jvertrees.hashnode.dev/the-most-important-file-in-your-repository-is-domainmd

### External Influences — Jim Snyder (Initial Links)

- **Liam Hsu (thesephist) — "Notational Intelligence"** — Notation shapes thinking. Good notation makes certain reasoning trivial. Computable notation can be executed.
  - https://thesephist.com/posts/notation/
- **OntoGPT (Monarch Initiative) — Ontology-grounded extraction** — Takes LinkML schema + free text → structured output (JSON, YAML, RDF, OWL). Zero-shot, ontology-grounded.
  - https://monarch-initiative.github.io/ontogpt/
- **Nishant Sharma — "Semantics as the Floor, Not the Ceiling"** — Deterministic semantics belongs at the foundation, not bolted on top.
  - https://www.linkedin.com/posts/nishant-sharma-73b3852_animesh-kumar-and-travis-thompson-s-latest-activity-7430073122441216001-jXn_
- **ThoughtWorks — "Future of Software Development Retreat"** — (PDF, content TBD)
  - https://www.thoughtworks.com/content/dam/thoughtworks/documents/report/tw_future%20_of_software_development_retreat_%20key_takeaways.pdf

### External Influences — Jim Snyder (Academic Papers)

**Cluster A — Biology needs engineering's formalism:**
- Lazebnik (2002) — "Can a biologist fix a radio?" Biology lacks formalized descriptive language.
- Hopfield (2014) — Physics-biology interface. Cross-discipline perspectives.
- Robinson & Iglesias (2012) — Physical sciences in cell biology research.
- Trewavas (2006) — History of systems biology. Emergent behavior in interconnected systems.

**Cluster B — Ambiguity is a feature of efficient communication:**
- Piantadosi, Tily & Gibson (2012) — All efficient communication systems are inherently ambiguous.
- Zipf (1949) — Principle of least effort. Ambiguity emerges from compression.
- Sterner (2022) — Polysemy in science: context-sensitive utility.
- Koçak, Park & Puranam (2022) — Ambiguity compensates for semantic differences in human-AI communication.
- Eisenberg (1984) — Strategic ambiguity as organizational communication strategy.

**Cluster C — Interdisciplinary knowledge & boundary objects:**
- Watkins & Elby (2013) — Context-dependent epistemology in biology education.
- Boon & Van Baalen (2019) — Engineering paradigm for interdisciplinary research.
- Star & Griesemer (1989) — Boundary objects: adaptable to different viewpoints, robust identity.

---

## Open Questions

1. **What is the minimal viable notation?** Start with a subset of system concerns (e.g., API contracts + auth flows)?
2. **How does the ambiguity gradient work in practice?** Zoom levels? Layer-based? Context-triggered resolution?
3. **How does the reconciliation loop detect and decompose deltas into agent work units?**
4. **What's the relationship between the spec and tests?** Derived from the spec, or part of it?
5. **How do you maintain boundary-object identity across viewpoints without lowest-common-denominator?** Which of Star & Griesemer's four types does the spec most resemble?
6. **How does the spec account for emergence?** Can emergent properties be encoded and validated, or is that the fitness/selection layer?
7. **What formal descriptive languages exist in systems biology post-Lazebnik?** Are there notations that bridge the bio/engineering divide?
8. **Does strategic ambiguity serve a coordination function in the spec?** Should teams be able to move forward without premature consensus on implementation?
9. **How do you version the spec?** Git-native?
10. **What's the trust model for agent-generated changes?** (Treasure Data principle: "AI writes code, but AI does not ship code.")
11. **How does this relate to existing tools:** Terraform, Pulumi, Backstage, Port, etc.?

---

## Next Steps

- [ ] Review and refine this vision doc (v2)
- [ ] Extract ThoughtWorks PDF content
- [ ] Research existing notation systems more deeply (LinkML, OWL, Alloy, TLA+, SBML, CellML)
- [ ] Sketch a minimal spec format for a toy system
- [ ] Write "Nature's Code Part 2" blog post — from metaphor to mechanism
- [ ] Evaluate: Heavy Chain product, open-source project, or thought leadership platform?
- [ ] Deepen collaboration with Jim Snyder — academic grounding + industry architecture perspective

