# Sector Accelerators

Curated, standards-aligned ontology starting points for common industries.
Each accelerator ships as a YAML file (Lakehouse-bound) and, where real-time
data materially changes the business value story, a companion `.eventhouse.ontology.yaml`
with KustoTable time-series bindings.

Tiny synthetic CSV sample data under `sample_data/<industry>/` lets every
accelerator generate a valid Fabric payload out of the box.

## Tier 1 catalog

| ID | Accelerator | Standards alignment | Telemetry layer | Folder |
|----|-------------|---------------------|-----------------|--------|
| B1 | Retail Banking - Customer 360 | BIAN service domains, FIBO entities | Card authorization stream | [accelerators/banking](banking/) |
| I1 | P&C Policy + Claims | ACORD Reference Architecture | Vehicle telematics (UBI / FNOL) | [accelerators/insurance](insurance/) |
| H1 | Patient 360 | HL7 FHIR R4 resources | Connected-device vitals (RPM) | [accelerators/healthcare](healthcare/) |
| T2 | Hotel / Property Mgmt | PMS / HTNG-OpenTravel | Room IoT (HVAC, occupancy, energy) | [accelerators/hospitality](hospitality/) |

## Files per accelerator

```
accelerators/<industry>/
  <subdomain>.ontology.yaml             # Lakehouse-bound core ontology
  <subdomain>.eventhouse.ontology.yaml  # Same ontology + time-series bindings
sample_data/<industry>/
  *.csv                                 # Tiny synthetic dataset, referentially consistent
```

## Generate a Fabric payload from any accelerator

Lakehouse-only (no Eventhouse required):

```bash
uv run fabric-ontology \
  --yaml accelerators/banking/retail_customer360.ontology.yaml \
  --workspace-id <workspace-id> \
  --lakehouse-id <lakehouse-id> \
  --output payloads/banking_c360.payload.json
```

With Eventhouse for the real-time variant:

```bash
uv run fabric-ontology \
  --yaml accelerators/banking/retail_customer360.eventhouse.ontology.yaml \
  --workspace-id <workspace-id> \
  --lakehouse-id <lakehouse-id> \
  --eventhouse-id <eventhouse-id> \
  --cluster-uri https://<cluster>.kusto.fabric.microsoft.com \
  --database-name <database-name> \
  --output payloads/banking_c360_rt.payload.json
```

## Per-accelerator business value summary

### B1 - Retail Banking Customer 360
Entities: `Customer`, `Household`, `Branch`, `Product`, `Account`, `Card`,
`Transaction`, `Merchant`, `Interaction`. Real-time variant adds card
authorization telemetry on `Card`.

- Next-best-action, attrition, cross-sell across products and channels
- Household-level profitability and AUM consolidation
- Real-time fraud / unusual-activity signals fed to the same Copilot
- Banker assistant: "summarise this customer", "why was this card declined"

### I1 - P&C Policy + Claims
Entities: `Party`, `Producer`, `Policy`, `Coverage`, `RiskObject`, `Claim`,
`ClaimFeature`, `ClaimPayment`, `Adjuster`. Telematics variant adds vehicle
telemetry on `RiskObject`.

- Loss ratio analytics across lines of business, producer scorecards
- Claims triage by severity, fraud likelihood, subrogation potential
- Usage-Based Insurance pricing and discount renewals
- Automated FNOL from crash signals; telematics-corroborated claims

### H1 - Patient 360
FHIR-aligned entities: `Patient`, `Practitioner`, `Organization`,
`Encounter`, `Condition`, `Procedure`, `MedicationRequest`,
`AllergyIntolerance`, `Observation`. RPM variant adds `ConnectedDevice` with
continuous vitals.

- Longitudinal patient view, readmission risk, care gaps
- Population health and value-based care reporting (HEDIS, CMS)
- Clinician Copilot: "summarise this patient", "what's changed since last visit"
- Remote Patient Monitoring and early-deterioration alerts

### T2 - Hotel / Property Management
Entities: `Guest`, `LoyaltyAccount`, `Property`, `RoomType`, `Room`,
`RatePlan`, `Channel`, `Reservation`, `Stay`, `Folio`, `FolioCharge`. IoT
variant adds room telemetry on `Room`.

- Revenue management (occupancy, ADR, RevPAR, length-of-stay)
- Channel mix optimisation and OTA cost-of-acquisition tracking
- HVAC setbacks on unoccupied rooms - typically 5-15% energy reduction
- Predictive housekeeping prioritised by real occupancy and DND status
- Real-time service: detect water leaks, temperature drift before the guest does

## What's coming next

Tier 2 candidates already on the roadmap:

- B3 Payments & Fraud (deep Eventhouse showcase)
- T1 Airline Operations & Loyalty (PNR/segment graph with disruption events)
- H2 Claims & Payer (payer-side companion to H1)
- B2 Commercial / SME Lending (covenant monitoring, portfolio risk)
