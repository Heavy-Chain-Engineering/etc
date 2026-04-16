# Integration Seams

Declares integration boundaries between bounded contexts. Each seam is verified
by `check-seam-evidence.sh` during the verify phase. See
`standards/process/invariants.md` for the companion invariant registry.

## SEAM-001: IAM to Relationships (user org membership lookup)
- **Producer:** src/venlink/iam/
- **Consumer:** src/venlink/relationships/
- **Interface:** `UserOrganizationMembership` model query
- **Integration test:** tests/integration/test_iam_relationships.py
- **Evidence level:** L2
- **Critical path:** Invitation approval flow
- **Concept:** UserOrganizationMembership

## SEAM-002: Salesforce ETL to Internal Models (status mapping)
- **Producer:** src/venlink/integrations/salesforce/
- **Consumer:** src/venlink/relationships/models/
- **Interface:** STATUS_MAP dictionary mapping Salesforce status strings to internal enum values
- **Integration test:** tests/integration/test_salesforce_status_mapping.py
- **Evidence level:** L3
- **Critical path:** Vendor onboarding via Salesforce sync

## SEAM-003: IAM to Search (tenant-scoped query filtering)
- **Producer:** src/venlink/iam/
- **Consumer:** src/venlink/search/
- **Interface:** `current_user.organization_id` filter applied to all search queries
- **Integration test:** tests/integration/test_search_tenant_isolation.py
- **Evidence level:** L3
- **Critical path:** All search operations

## SEAM-DEV-001: Dev simulation to Approval flow (fixture fidelity)
- **Producer:** src/venlink/dev/routes.py
- **Consumer:** src/venlink/relationships/invitation_service.py
- **Interface:** Dev simulation creates entities consumed by approval flow
- **Constraint:** Dev simulation MUST create entities that satisfy the same invariants as production creation (e.g., vendor org must have at least 1 admin user)
- **Integration test:** tests/integration/test_dev_simulation_fidelity.py
- **Evidence level:** L3
- **Critical path:** Dev/QA testing of approval flow

## SEAM-DEV-002: Test fixtures to Compliance checks (fixture fidelity)
- **Producer:** tests/fixtures/compliance_data.py
- **Consumer:** src/venlink/compliance/checker.py
- **Interface:** Test fixtures produce compliance records consumed by the checker
- **Constraint:** Fixture compliance records MUST include all required fields that production records contain (no silent nulls)
- **Integration test:** tests/integration/test_compliance_fixture_fidelity.py
- **Evidence level:** L2
- **Critical path:** Compliance audit verification
