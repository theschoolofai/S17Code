---
name: a2ui
description: This skill should be used whenever the run has to produce a user interface rather than prose. Load it before adding a compose_surface node, and whenever the request asks to "show", "display", "render", "make an app", "build a page", "make it interactive", or asks for a quiz, exercise sheet, dashboard, form, report or worksheet. It carries the closed component catalog, the data-binding rule, and four behaviours of the render client that are not guessable.
when_to_use: the run will end in a surface instead of an answer
keywords: [surface, interface, ui, render, quiz, exercise, dashboard, worksheet]
---
You are composing an A2UI surface. Read this before you plan the nodes, not after.

## The shape you produce

A surface is three things and no markup:

```json
{
  "root": "col_main",
  "components": [ {"id": "...", "type": "...", ...}, ... ],
  "dataModel": { "title": "...", "questions": [...] }
}
```

`components` is a flat array linked by `id`, not a nested tree. A parent names its
children by id in a `children` list. One component is the `root`.

## The rule that matters more than any other

**You compose structure. You do not author data.**

The harness builds the data model from what the run actually produced, and hands
you the list of pointers that exist as `available_pointers`. Your job is to
choose components and bind them to those pointers.

```json
{"id": "q1_stem", "type": "Text", "variant": "body", "text": {"$bind": "/item_0_detail"}}
```

**Bind only to a pointer that appears in `available_pointers`.** A pointer you
invent resolves to nothing. The surface will still validate, because the
structure is legal, and it will render with every field blank. That failure is
silent: no rejection, no error, an interface full of empty cards.

Read `available_pointers` first and design the layout around what is genuinely
there. If the data you want is not in the list, the fix is upstream: the node
that produced the content needs to emit it as structured data, not prose. Do not
paper over it by inventing a path.

Values you may write literally are the ones no user supplied: a `Card` title, a
`Tabs` label, a section heading. Everything that came from the run is a binding.

**Inputs are the exception, and it is easy to get wrong.** For `TextField`,
`CheckBox`, `InputChoice` and `Slider`, the `value` binding is where the answer
is *written*, not where content is read from. It should point at a fresh pointer
under `/input`, one per control, and it will be empty until the user acts. That
is correct: an unanswered question has no answer.

    options -> a pointer that exists and holds the choices  (read)
    value   -> /input/q0                                     (write)

Do not point a `value` at content, or the first keystroke overwrites it.

## Four things about the render client you cannot guess

**`Modal` does not hide anything.** The client draws it as a labelled block and
always renders its children. If you put answers in a `Modal`, they are on screen
immediately. Never use `Modal` to conceal.

**`Tabs` genuinely conceals.** It renders only the active panel; the others are
not in the DOM until clicked. `Tabs` is the only concealment you have. Each child
of a `Tabs` is one whole panel, and `labels` is a comma-separated string naming
them in order.

**Buttons do four things and each is a server round-trip.** `onPress` accepts only
`approve`, `reject`, `request_data`, `rerun`. There is no `submit` and no `reveal`.
If your design needs a button that does something else, the design is wrong: use
`Tabs` for progressive reveal and inputs for local state.

**`Text` with `variant: "heading"` is rendered literally; `body` is rendered as
safe markdown.** Put `$x^2$`-style plain text in body variants and it survives.

Inputs (`TextField`, `CheckBox`, `InputChoice`, `Slider`) write straight back into
the data model in the browser, so a learner can select answers with no round-trip.

## Composing an exercise or quiz

This is the pattern that works with the constraints above:

- `Tabs` at the top with `labels: "Questions, Solutions"`.
- Panel one: a `Column` of `Card`s, one per item. Each card holds a `Text` (body)
  bound to the pointer carrying that item's question, and an `InputChoice` bound
  to the pointer carrying its options.
- Panel two: a `Column` of `Card`s bound to the pointers carrying the solutions.

The learner answers in tab one and checks in tab two. No buttons, no actions, no
round-trip, and nothing is spoiled because tab two is not rendered until clicked.

Every one of those bindings must come from `available_pointers`. If the run
produced ten questions but the only pointers are `/item_0_label` and
`/item_0_detail`, then that is what you bind, and the layout follows the data you
have rather than the data you wish you had.

Use `Notice` with `tone: "warn"` to carry an instruction like "attempt before
opening Solutions".

## Before you finish

Call `load_skill` with `reference: "catalog.md"` to get every component type and
its exact properties. Do that before composing rather than guessing a property
name: a type or property that is not in the catalog is rejected by the validator,
and the rejection names the component and the field.

Keep the data model flat and boring. Arrays of objects with short keys bind
cleanly; deep nesting produces pointers nobody can read.
