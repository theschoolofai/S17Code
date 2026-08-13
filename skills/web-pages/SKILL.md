---
name: web-pages
description: This skill should be used whenever the run creates or edits an .html file, or the request mentions a page, a site, a landing page, CSS or the browser. It carries the harness command and the two failures that make a page look fine to the author and blank to everyone else.
when_to_use: an .html file is being written and has to work in a real browser
keywords: [html, page, landing, css, browser, frontend, website]
---
A page that renders on your machine has not been checked. Before you answer,
run the harness:

```
node webcheck.js <file>
```

It loads the page in a real DOM, on a `file://` origin where storage APIs throw,
and again with JavaScript switched off. It fails if a person would see a blank
page.

Two failures account for most of what it catches.

**Storage on an opaque origin.** `localStorage.getItem` throws on `file://`. If
it runs at the top of your script, everything below it never runs, including
whatever reveals your content. Wrap the read in `try`/`catch`. Do not delete the
feature: removing persistence makes the check pass and loses the behaviour that
was asked for.

**Content hidden by an entrance animation.** If `.reveal { opacity: 0 }` lives in
plain CSS, the page is blank with JavaScript off. Put the hiding rule behind a
class that JavaScript adds, so the content is visible when the script never runs.

If webcheck reports a failure, fix the cause and run it again. Do not report
success while it is still returning non-zero.
