# Part Number: Role in the Design

Replace the title, fill in every section and delete this line.

| Field | Value |
| --- | --- |
| Status | Accepted, accepted with conditions, or rejected |
| Date | YYYY-MM-DD |
| Specification | Sections that use the part and the section 16 item |
| Schematic | Reference designators and sheet in the draft or revision checked, for example "U27, Signal Chain, draft A2" |
| Datasheet | Title, document number, revision, date and link |

## Questions

What the design needs from this part. Trace each question to a section or a
requirement of the specification.

1. Question.

## Findings

Quote the datasheet. Give the test condition for every value and use the
guaranteed limits, not the typical value, for worst-case analysis.

| Parameter | Condition | Min | Typ | Max | Unit | Source |
| --- | --- | --- | --- | --- | --- | --- |
| Parameter | Condition | | | | | Page, table or figure |

A value the datasheet does not state is recorded as "not specified" and
becomes a measurement item for a development phase.

## Symbol and Footprint

The comparison is part of every check. Pin numbers and pin names of the
schematic symbol against the pin table of the datasheet, and the land
pattern of the footprint against the drawing of the manufacturer: pad
count, pitch, pad size, thermal pad and the position of pin 1. Name the
library the symbol and the footprint come from, and say so when one of them
was drawn for the project. A subject without a package, such as a
peripheral of the controller, states "not applicable".

## Analysis

Design value against the datasheet limits, worst case and margin, with the
calculation shown. A figure that the specification marks "calculated",
"simulated" or "estimate" keeps that mark here: the record can confirm the
datasheet values behind it, and its measurement stays open until a report
holds it.

## Verdict

The decision, the conditions the design must respect and any follow-up
measurement.

## Changes to the Specification

Sections updated as a result, the item of section 16 and the row of the
table in the [index of the checks](README.md), and the decision log entry
if a part or a design value changed. A change to the schematic or the board
that follows from the record is named here too.
