# ADR-0003: Expected attendance must be at least 1, with no upper limit

- **Status:** Accepted
- **Date:** 2026-09-15
- **Story:** SCRUM-19 Submit an event request (AC2: expected attendance is required)

## Context
The AC makes expected attendance required but sets no valid range. Zero or negative numbers make no sense. An upper limit could depend on venue capacity, which isn't modelled yet.

## Decision
- `expected_attendance` must be a whole number **of at least 1**.
- Strings like `"50"`, decimals, and booleans are rejected, not converted.
- There is **no upper limit**. The organiser is responsible for choosing a realistic figure, including any buffer.

## Consequences
- Simple validation: `fields.Integer(strict=True, validate=Range(min=1))`.
- Unrealistic figures such as 10,000,000 are accepted and must be caught when a coordinator reviews the request.

## Revisit when
- Venues and their capacities are modelled, so attendance can be checked against real limits.
- The business defines event size tiers or a maximum.
