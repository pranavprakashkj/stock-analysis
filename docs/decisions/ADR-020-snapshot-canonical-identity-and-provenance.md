# ADR-020: Snapshot identity from canonical logical content; provenance recorded separately

## Status
Accepted (owner-directed remediation, 2026-10-05). Refines ADR-010 ("snapshot id = content hash") and ADR-017's use key.
The canonicalisation and hashing are implemented in Phase 1 (remediation). Storage of snapshots (Parquet) remains Task 1.11.

## Date
2026-10-05

## Context
Hashing Parquet bytes ties snapshot identity to writer details: compression, row-group layout, metadata, Polars version.
Identical data could get a new id after a library upgrade. Because ADR-017's use key includes snapshot hashes, that could cost a holdout use.

## Decision

### 1. Snapshot identity = SHA-256 over a canonical serialisation of the logical table
Canonicalisation version `canonical-v1`. This section is the normative byte layout; an independent implementation written from it must reproduce the ids (test-enforced).

**Notation:** `u64(n)` = 8-byte big-endian unsigned integer; `L(b)` = `u64(len(b)) ‖ b`; `‖` = concatenation; text is UTF-8.

1. **Schema:** a list of columns `(name, type, nullable)`. Columns are sorted by name in Unicode code-point order. Duplicate names are rejected.
   The schema is part of the logical content: changing a type, scale, name or nullability changes the id.
2. **Types (closed set) and canonical text of a value:**

   | Type text | Accepted value | Canonical text |
   |---|---|---|
   | `STRING` | `str` | the string itself, **not** Unicode-normalised (NFC and NFD differ; parsers normalise at ingestion if a source needs it) |
   | `INT64` | `int` in signed 64-bit range (`bool` rejected) | decimal digits with optional leading `-` |
   | `DECIMAL(s)` | finite `Decimal` with at most `s` significant places after the point (trailing zeros beyond `s` allowed), and at most 38 digits in total counting the scale padding (bounds hashing time; matches the common decimal128 precision, re-checked against storage in Task 1.11) | optional `-` (never for zero), integer digits (at least one), then `.` and exactly `s` digits when `s > 0`. Computed without any decimal context |
   | `DATE` | `date` (a `datetime` is rejected) | `YYYY-MM-DD` |
   | `TIMESTAMP_UTC` | timezone-aware `datetime` | converted to UTC, `YYYY-MM-DDTHH:MM:SS.ffffffZ` with a 4-digit zero-padded year (ISO-8601 rendering) |
   | `BOOL` | `bool` | `true` or `false` |

   **No floating-point type.** Wrong types are rejected; nothing is coerced. Storage precision of decimals (e.g. Parquet `DECIMAL(p, s)`) is a storage concern and not part of identity.
3. **Cell:** null → `0x00` (allowed only in nullable columns); value → `0x01 ‖ L(canonical text)`.
4. **Row:** the cells of all columns in canonical column order, concatenated. Rows are sorted bytewise by this encoding; duplicates keep their multiplicity.
5. **Hash input:** `L(tag) ‖ u64(column count) ‖ for each column: L(name) ‖ L(type text) ‖ (0x01 if nullable else 0x00) ‖ u64(row count) ‖ for each sorted row: L(row)`.
   The tag is `canonical-v1` for snapshots and `manifest-v1` for source-file manifests, so the two id spaces never collide.
6. **Hash algorithm:** SHA-256, lowercase hex.

Consequence: the same logical rows produce the same id regardless of input row order, input column order, or how the table is later
serialised to Parquet. Any change to a value, a type, a column name or the row multiset produces a different id.

### 2. Provenance is recorded separately and is not part of the snapshot id
Each snapshot carries a **source-file manifest**. Each entry records:
- file name
- SHA-256 of the raw file bytes
- acquisition time, if known
- source/provider (e.g. `nse-files`)
- format and format version (e.g. `nse-cm-bhavcopy-legacy`, `nse-cm-bhavcopy-udiff`)

- The manifest has its own hash, recorded next to the snapshot id in run manifests.
- Re-acquiring identical data from a different file or at a different time leaves the snapshot id unchanged and changes the manifest. A changed source file with changed content changes both.

## Alternatives Considered
- **Hash the Parquet file bytes:** unstable across writers and versions, as above.
- **Hash a CSV or JSON dump:** delimiter, escaping and float-formatting ambiguity.
- **Include provenance in the id:** identical data acquired twice would look like different data.

## Consequences
- Task 1.11's store writes Parquet but identifies snapshots by the canonical hash. Its acceptance includes a Parquet round-trip test: write → read → re-hash gives the same id. That test needs Polars, which is installed with Task 1.7/1.11 and not before.
- Date-partitioning by knowledge-time window (ADR-018 §2) is part of the snapshot metadata in Task 1.11.
