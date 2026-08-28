# Data Sources

## Overview

All clinical and organisational content used in this project is **purpose-built seed data**
created for the assessment. It is not sourced from, derived from, or representative of any
real patient records, clinical databases, or external data providers.

## What the data contains

| Dataset | Location | Description |
|---|---|---|
| Organisation | `supabase/seed.sql` | One fictional hospital — *Supra Multi-Specialty Hospital* |
| Hierarchy levels | `supabase/seed.sql` | 15-level DAG structure (divisions → departments → specialties) |
| Knowledge nodes | `supabase/seed.sql` | ~50 fictional clinical/administrative knowledge nodes |
| Users | `supabase/seed.sql` | 7 fictional staff users across roles (VIEWER, HOD, ADMIN, etc.) |
| Schema | `supabase/schema.sql` | PostgreSQL table definitions — no external schema standard applied |

## Data provenance

- **No real patient data** is present anywhere in this repository.
- **No external clinical terminology standards** (ICD-10, SNOMED, HL7, FHIR, etc.) were used
  or referenced. All node names, tags, and department names are illustrative placeholders.
- **No third-party data licences** apply. The seed data was written from scratch as part of
  the assessment brief.

## Reproducibility

Any reviewer can fully reproduce the dataset by running the two SQL files against a fresh
Supabase project as described in the [README](./README.md#2-supabase-setup). There are no
external API calls, file downloads, or proprietary data dependencies.
