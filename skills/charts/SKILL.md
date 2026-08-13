---
name: charts
description: This skill should be used when a surface needs to show numbers rather than text: trends, comparisons, totals, distributions, progress, or a sequence of dated events. Load it alongside a2ui whenever the request mentions data, metrics, results, scores, a breakdown, a comparison, or "how it changed". It says which of the five data components to pick and what shape each one binds to.
when_to_use: the surface has to display quantities, not sentences
keywords: [chart, graph, data, metrics, results, scores, trend, comparison, dashboard]
---
Five components show numbers. Picking the wrong one is the usual mistake, so pick
by the question the reader is asking.

| The reader is asking | Use | Binds to |
| --- | --- | --- |
| how do these compare? | `BarChart` | array of objects, plus `xKey` and `yKey` naming two fields |
| which way is it going? | `Sparkline` | a flat array of numbers |
| what is it now? | `StatTile` | one value, optional `delta` |
| how far along? | `ProgressBar` | one number, with `max` |
| what happened, in order? | `Timeline` | array of dated events |
| all of the rows | `DataTable` | array of objects, with `columns` as a comma list |

Rules that hold for all of them.

**The data goes in the data model, never in the component.** `data`, `rows`,
`value`, `events` are bindings. The component names a pointer; the numbers live at
that pointer. Same rule as every other value in a surface.

**A chart with one number is a `StatTile`.** A bar chart of a single bar tells the
reader nothing they could not read from a label.

**A `StatTile` needs a unit.** "94" is not a fact. "94 %" and "94 marks" are
different facts, and `unit` is a separate property so the number stays numeric.

**Tone is a claim, so only make it when you can support it.** `tone` on a
`StatTile` or `Sparkline` renders as good or bad. Set it from the data, not from
the mood of the surrounding text. Leave it `neutral` when up is not obviously
better than down.

**A `DataTable` earns its place when the reader will scan or sort.** Under about
five rows a `List` of `Text` is easier to read. Set `sortable` when the order is
genuinely a question the reader has.

For a marks or scoring summary, the shape that reads well is a `Row` of two or
three `StatTile`s across the top, then one `BarChart` broken down by topic, then a
`DataTable` for the detail underneath.
