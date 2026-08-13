---
name: bento-slides
description: This skill should be used when the request is for a slide deck, a presentation, a talk, a pitch, or "make some slides about X", and a .bento.html file is available in the workspace. Bento decks are a single HTML file whose slide data is JSON near the top, so making slides is editing that JSON. Carries the document location, the element schema, the morph rule, and the one escaping mistake that silently destroys the file.
when_to_use: the deliverable is a presentation rather than a page or an answer
keywords: [slide, slides, deck, presentation, talk, pitch, keynote, bento]
---
A Bento deck is one `.bento.html` file that is the document, the editor and the
player at once. Making slides means editing JSON inside that file. You are not
writing HTML, CSS or JavaScript.

## Before anything else

**The base file must already be in the workspace.** You cannot download it: the
command runner has no network client on its allowlist. Check first:

```
glob_files("**/*.bento.html")
```

If there is no such file, stop and say so plainly. Do not hand-write an HTML
file and call it a Bento deck; the player is the other 99% of that file.

**The app file arrives with an empty deck**, which is what you want:

```html
<script type="application/bento+json" id="bento-doc"></script>
```

Your job is to fill that in, not to perform surgery on an existing document.

**Copy the base file first. Do not create a new one.**

```
copy_code_file(source="Bento_Slides.bento.html", destination="attention.bento.html")
```

`create_file` cannot do this: it refuses to overwrite the base, and it could not
reproduce 690 KB it has not read anyway. The command runner cannot do it either:
`python -c` is refused as an unbounded shell, and there is no copy program on the
allowlist. `copy_code_file` is the one route, and the copy is editable
immediately because nothing was read into the model to begin with.

Then edit the copy. Gallery templates are also valid decks but they embed images
as data URIs, over a megabyte of base64 on one line: never use one as a base.

**Never read the whole file.** It is around 690 KB, almost all of it the embedded
player and fonts. Find the block and read only around it:

```
grep_code("bento-doc")          -> the line number (94 in the current release)
read_code(path, start, end)     -> a small window
```

## Where the deck lives

```html
<script type="application/bento+json" id="bento-doc">
{ "format": "bento/slides", "version": 1, "title": "...", "size": {...},
  "theme": {...}, "slides": [ ... ] }
</script>
```

Top level: `format` must be `"bento/slides"`, `version` is `1`, and `title`,
`size` and `theme` are required. `slides` is the array you will mostly edit.
`assets`, `fonts`, `layouts` and `meta` are optional.

**If `docId` is present, it is an identity, not a value: never regenerate it.**
A fresh app file and the gallery templates both ship without one, so its absence
is normal and not something to fix.

`size` is an object, `{"width": 1280, "height": 720}` in the current release.
Read it rather than assuming it.

## The escaping rule that destroys files

**Every `<` inside the JSON must be written `<`.**

This is not theoretical. The shipped `signal` template contains zero literal `<`
and twelve escaped `\u003c`, because a literal `<` anywhere in the JSON closes
the surrounding `<script>` tag early.
The browser then parses the rest of your deck as HTML, and the file is silently
ruined: it still opens, and it is empty. This bites hardest in `text` elements,
whose `html` field is the place you are most likely to type a tag.

## A slide

```
id          unique
elements    the array of things on the slide
transition  "none" or "morph"
background  hex colour
notes       speaker notes
stateOf     parent slide id, making this a hidden drill-down variant
hidden      skipped during presentation
```

## An element

Every element has `id, x, y, w, h, rotation, opacity`. Then by type:

| type | the fields that matter |
| --- | --- |
| `text` | `html`, `fontSize`, `fontFamily`, `fontWeight`, `color`, `align`, `valign`, `lineHeight` |
| `shape` | `shape` (rect, ellipse, triangle, arrow, line, path), `fill`, `stroke`, `strokeWidth`, `radius` |
| `image` | `src` (a data URI or `"asset:key"`), `fit`, `radius` |
| `chart` | `preset` (bar, line, pie, scatter), `option` (ECharts-shaped) |
| `table` | `columns`, `rows`, `header`, `style` |
| `media` | `kind` (video or audio), `src`, `controls`, `autoplay`, `loop`, `muted` |
| `svg` | `asset` or `markup` |

Chart data for bar and line must be plain numbers, not objects.

## Morph is the whole reason to use this

Set `transition: "morph"` on the **later** slide. Any element whose `id` matches
one on the previous slide tweens: position, size, colour, gradients. Elements
with no partner fade in.

So a title that shrinks and moves to the corner is one element with the same id
on both slides, at different `x`, `y` and `fontSize`. It is not two elements and
not an animation you write.

Use `morphId` when you want two elements to morph into each other but need their
`id` values to stay distinct.

## Layout

The canvas is **1280 × 720** in the current release, but read `doc.size` rather
than trusting that.
Side margins are 96, so content must end by x = 1184.

One accent colour. At most two typefaces. A deck that uses four is not a deck
with range, it is a deck nobody edited.

## Check your work before you answer

The player ships its own validator, so use it rather than reasoning about
whether the JSON is right:

```
window.bento.validate()   structure, overflow, broken links, duplicate ids
window.bento.measure({html, w, fontSize, lineHeight})   size text before placing it
```

Run these in a browser context, the same way the web-pages skill runs its
harness. A deck that validates clean is not automatically a good deck, but a
deck that fails validation is definitely a broken one.

## Editing, concretely

**Writing the first deck.** The empty tag pair appears exactly once in the file,
so it is a unique anchor and the whole deck goes in with one edit:

```
old_string:  <script type="application/bento+json" id="bento-doc"></script>
new_string:  <script type="application/bento+json" id="bento-doc">
             { "format": "bento/slides", ... }
             </script>
```

Read the file around line 94 before you do this. An edit to a file this run has
not read is refused, and the refusal is correct.

**Changing a deck that already has content.** Now the JSON is one very long line,
so replace a unique inner fragment rather than the whole document: anchor on a
slide `id` with enough surrounding text to name one place. If the anchor matches
twice the edit is refused, and the fix is more context, not `replace_all`.

**After every edit, re-read the range you changed.** A JSON syntax error inside
that block raises nothing at edit time. It shows up later as a deck that opens
blank, which is indistinguishable from a deck you never wrote.
