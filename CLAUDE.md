# DBML renderer

## Application Goals

- Read the provided dbml file (`python app.py --dbml test.dbml --db test.db`) in a flask app.
- The app is a CRUD interface.  Everything we need the app to do and behave is in the dbml file.
- We first start vanilla - take the dbml as is.  Each table in the dbml gets rendered as a CRUD interface.  Menu item, table, form, the works.
- Any link to another table should be a modal selection, showing that other table, and allowing the to select the item.  Of course, we also allow that modal to be a full CRUD interface - the user can add a new item if needed.
- Respect the data model - if there is a link to a foreign key, you cannot delete a record if the linkage has to hold.
- enums are dropdows - obviously.

## Scope

**Who can touch what, never when.** The app renders data and decides access by role, table and column only. Rules that depend on a record's data or stage (workflow, approvals, hand-offs, "only one department edits at a time", row ownership) are business logic and out of scope. A workflow can still be modelled by hand, e.g. an enum `stage` column people change themselves; the app just does not enforce who may edit at each stage.

## Guiding principle

**Look like an application, not a development tool.** The generated app should feel as close to a real, functional application as possible. Schema details (column types, keys, table or record counts, generated ids) stay out of the UI; the DBML shows through only as the app's names, notes, colours and behaviour.

**Stay true to DBML: render what the dbml says, and infer only where the dbml is silent.** Anyone should be able to drop in an existing dbml file and see a working app straight away, without learning conventions of our own. Where the app has to fill a gap the dbml leaves open (e.g. the display column, default delete behaviour, join table naming), it says so in this file, and prefers what DBML's own tooling does.

## Decisions

- **Storage: SQLite.** DDL is generated from the dbml at startup so the database itself enforces `pk`, `unique`, `not null`, enums (`CHECK` constraints) and foreign keys (`PRAGMA foreign_keys=ON`, `ON DELETE RESTRICT`).
- **Parser: our own, `crud/dbml.py`.** One self-contained file (standard library only, no imports from the app) with a `DBML` class: `DBML(source)` parses the full DBML spec, applies `TablePartial` injection, resolves aliases and schemas, and raises `DBMLError` with line and column for invalid DBML. It replaced `pydbml`, which had stopped keeping up with the spec. **dbdiagram.io is the reference:** where the docs and dbdiagram disagree, the parser follows dbdiagram. `tests/monster.dbml` exercises every feature and must validate on dbdiagram.io; `tests/test_dbml.py` asserts on it section by section.
- **CSRF protection:** `flask-wtf` guards every POST; each form carries a `csrf_token`. A refused post (e.g. a form left open across a restart without `SECRET_KEY` set) shows "This form has expired" and returns to the page it came from (JSON for the picker modal).
- **Configuration:** the dbml file and SQLite database paths are both required. Supply them with `--dbml` / `--db` on the command line, or with `DBML=` / `DB=` in a `.env` file. Command-line arguments take precedence over `.env`. If either path is missing from both, the app exits with a clear error.

## Assumptions

- Security is not the target state - the goal is to show if this is feasable.
- Foreign key display column: when showing a linked record (in tables, forms and the selection modal), use the first `unique` text column of the referenced table, falling back to its first text column, then to the primary key.
- uuid has no SQLite type. Store it as TEXT and generate it in Python with uuid4().
- The dbml mirrors the database: table and column names are kept exactly as written in the dbml and in SQL. Only where a table, column or project name is **displayed** is it turned into a label by `crud/labels.py`: underscores become spaces and each word gets a capital first letter (`order_number` → `Order Number`; the rest of each word is untouched, so `MFA_status` → `MFA Status`). Common acronyms written in lower case are put in capitals from a fixed built-in list (`metric_id` → `Metric ID`, `slo_min` → `SLO Min`); a word the author capitalised is left as written. URLs, form field names and SQL always use the raw name. Table group names, enum values and notes are author-written text and are shown as written.
- In SQL, names are currently also used exactly as written (quoted). Whether to sanitise them when they hit the database (e.g. `Order Item` → `order_item`), and whether to warn about naming style, is an open question to revisit later — not a decision.
- Two table names, or two column names in the same table, that differ only by case cannot both be used (SQLite matches identifiers case-insensitively): the affected table is skipped with a warning.

## Support for DBML

The goal is to fully support DBML ([spec](https://dbml.dbdiagram.io/docs/)) so an application can be rendered and prototyped rapidly from the dbml alone. `[x]` = supported and verified; `[ ]` = still to do.

**Parsing is complete:** `crud/dbml.py` reads every feature below. The checklist tracks what the **app** does with each one.

**Invalid DBML stops startup; unsupported DBML never does:** a file that is not valid DBML is a parse error with its line and column. Valid DBML the app cannot render yet is skipped with a logged warning naming it, and the rest still renders.

### Project, schemas and layout

- [x] `Project` name — app title and navbar brand
- [x] `Project` note — shown on the home page
- [ ] `Project` settings (`database_type` and custom settings) — parsed, unused
- [ ] Schemas (`schema.table`) — parsed and resolved (`public` is the default); the app ignores the schema, so same-named tables in different schemas: the second is skipped with a warning
- [x] Cross-schema refs — resolved by the parser
- [x] `TableGroup` — collapsible headings in the sidebar (closed groups remembered per browser; the group holding the current page always opens) and sections on the home page (with the group note); ungrouped tables under "Other tables"
- [ ] `TableGroup` `color` — parsed, unused
- [x] Sticky notes (`Note name { ... }`) — shown on the home page
- [x] Comments (`//` and `/* */`)
- [x] Multi-line strings (`'''...'''`), including a trailing `\` to join lines

### Tables

- [x] Each table rendered as CRUD — menu item, searchable/sortable/paged list, new/edit forms, delete with confirmation
- [x] Table note (`Note:`, `Note { }` or `[note: ]`) — shown on the home page card, list page and form page
- [x] Table alias (`Table x as X`) — refs, groups and records through the alias resolve
- [x] Table and column names used exactly as written, including quoted names with spaces and capitals (`"Order Items"`, `"Unit Price"`)
- [x] Table, column and project names displayed as labels (`order_number` → `Order Number`); raw names everywhere else
- [x] Names differing only by case — the later table (or the table with clashing columns) is skipped with a warning
- [ ] Decide: sanitise names in the database (`Order Item` → `order_item`) while keeping them as written in the UI, and/or warn about naming style
- [x] `headercolor` — the table's colour (sidebar swatch, home tile, page title, row hover, related-records heading); must be a hex colour
- [ ] Custom table properties — parsed, unused
- [x] `TablePartial` and `~partial` injection — expanded where `~partial` appears; the table's own columns win, then the later partial; indexes, checks, note and settings carried over

### Columns

- [x] Types: integer family, float/decimal/numeric, bool, date, datetime/timestamp, uuid, text family; size suffixes (`varchar(255)`) stripped
- [x] `text` (and `mediumtext`, `longtext`, `ntext`, `clob`) → multi-line text area that starts at ~3 rows and grows with its content; left out of list tables (still searchable)
- [x] `varchar`, `char`, `string` and unrecognised text types → single-line input, shown in list tables (long values clipped, full value on hover)
- [x] `varchar(n)` / `char(n)` length → enforced on save ("Maximum n characters") and by the input's `maxlength`; SQLite itself ignores it
- [x] Quoted multi-word types (`"double precision"`, `"character varying(n)"`, `"timestamp with time zone"`)
- [x] Unrecognised types — treated as single-line text, with a startup warning per type
- [ ] Array types (`int[]`) — parsed; treated as text
- [x] `pk` — single-column primary key; integer and uuid keys are generated by the app
- [x] Generated primary key never shown on the form (the app should read as an application, not a database tool); hidden from list tables, unless the table has no other column to show there (e.g. only `text` columns) — then it is the list's muted first column
- [x] `primary key` long-form spelling
- [x] `not null` / `null`
- [x] `unique`
- [x] `default:` literal (number, string, boolean, null) — pre-fills the new-record form
- [ ] `default:` written into the table DDL
- [ ] `default:` expression (`` `now()` ``) — parsed, unused
- [ ] `increment` — parsed; honoured implicitly for integer primary keys only
- [x] Column `note` — help text under the form field, and a tooltip on the list column header
- [x] Notes rendered as Markdown (project, table, group, column and sticky notes) — raw HTML escaped, unsafe links refused; enum value hints stay plain text
- [ ] Column `check:` constraint — parsed, not enforced
- [ ] Custom column properties — parsed, unused

### Indexes

- [x] Single-column index
- [x] Composite index
- [x] `unique` — enforced by the database, friendly error in the form
- [x] `name:`
- [x] Index columns must exist — otherwise a parse error
- [ ] `pk` index (composite primary key) — table skipped with a warning
- [ ] Expression index — parsed; skipped with a warning
- [x] `type: btree | hash` — parsed and ignored (not applicable to SQLite)
- [ ] Index `note` — parsed, unused

### Checks

- [ ] `checks { ... }` block with `name:` — parsed, not enforced

### Relationships

- [x] Inline form (`[ref: > t.c]`)
- [x] Short form (`Ref: a.c > b.c`)
- [x] Long form (`Ref name { ... }`) — exactly one relationship per block, as dbdiagram requires
- [x] `>` and `<` — modal picker on the form; label shown in lists; searchable and sortable by label
- [x] `-` one-to-one — picker like many-to-one, plus a unique index so each record is linked at most once
- [x] `<>` many-to-many — join table generated as `{table1}_{table2}` (DBML export naming); multi-select chips on both forms; not shown in lists (a list is for scanning; links are edited on the form)
- [ ] `<>` self-referencing (`a.id <> a.id`) — ref skipped with a warning
- [ ] More than one `<>` between the same two tables — extra refs skipped with a warning
- [ ] Optional relationships (`>?`, `?<`) — parsed (which side is optional); the app treats them like the plain operator, nullability comes from the column
- [ ] Composite foreign keys (`t.(a, b) > u.(x, y)`) — parsed; ref skipped with a warning
- [x] `delete:` actions — passed to the database. Defaults: not-null FK → `restrict`, nullable FK → `set null`, `<>` link → `cascade` (removes only the links)
- [ ] `update:` actions — parsed, unused
- [ ] Ref `color` — parsed, unused

### Enums

- [x] Enum → dropdown, enforced with a `CHECK` constraint
- [x] Quoted values with special characters (`"A+"`, `"on hold"`)
- [x] Enum value notes — shown under the dropdown for the selected value
- [x] Schema-qualified enums (`core.job_status`)
- [x] `Note` inside an `Enum` — rejected (not valid DBML; dbdiagram allows notes only in Table, TableGroup, TablePartial and Project)

### Records (sample data)

- [x] `records` blocks (inside a table, or top-level `records table(cols)`) — loaded when a table is first created, all or nothing, foreign keys checked at the end so order does not matter; `now()` / uuid functions evaluated, other expressions warned about
- [x] Values: strings (with escapes, commas, multi-line), numbers (negative, decimal, exponent), booleans (any case), `null`, empty fields, trailing commas, enum constants (`status.done`), expressions
- [x] `records` with a settings list (e.g. `[example]`) — rejected (not valid DBML; dbdiagram rejects it)
- [ ] Records for `<>` links — not expressible in DBML (join tables are implicit); links are made in the app

## Backlog

Not started; roughly in priority order. Detail is from the design discussion so the reasoning is not lost.

- [ ] **Get the work into git.** The `appspec` repo has nothing committed (everything untracked on `main`). Create a working branch and commit.
- [ ] **CRUD: related records on the parent form.** E.g. an Order shows its Order Items, with add/edit/delete in place (the picker modal already does nested CRUD). `Table.referenced_by` already has what is needed.
- [ ] **CRUD: per-column filters.** Dropdowns for enums and booleans, a record picker for foreign keys, date ranges; held in the URL. The single all-column `LIKE` search stops being enough past a few hundred rows.
- [ ] **CRUD: read-only detail view.** At the moment the edit form is the only way to look at a record.
- [ ] **CRUD: bulk actions.** Select rows to delete, or to set one field on all of them. Pairs naturally with CSV import/export.
- [ ] **CRUD: composite primary keys** (`indexes { (a, b) [pk] }`). Currently the table is skipped; real-world dbml (explicit join tables, history tables) uses them often.
- [ ] **Authentication.** Reuse the Google sign-in from the `massyn:flask` golden template rather than building login. This changes the "security is not the target" assumption above — update it when this starts.
- [ ] **Authorisation: `app.yaml` roles.** Who can touch what. DBML describes data, so access rules live in a companion `app.yaml` next to the dbml (YAML, via PyYAML), versioned and reviewed like code. It is the application *definition*; *which user holds which role* is app data, kept in the app's database and managed from an admin screen. Decided shape: one `roles:` section, no separate table-behaviour section (a read-only table is simply one no role may write):

  ```yaml
  roles:
    everyone:                       # every user, signed in or not
      "*": [read]
    editor:
      "*": [read, create, update]
      framework_reference: [read]
    admin:
      "*": all
      framework_reference: [read]
      audit_log: [read, create]
  ```

  Rules: actions are `read`, `create`, `update`, `delete` (`all` for every one); changing a record's many-to-many links is `update`; the picker needs `read` on the table it shows. Deny by default; a user's rights are the union of their roles (roles only add). Within a role the most specific key wins: table, then TableGroup name, then `"*"`. No `app.yaml` at all means everything is allowed, so a bare dbml still just works. Enforced on the server in every list, read, save and delete, not just by hiding UI. Comes after authentication. Open question: `../spec.md` rules out a manifest for *routing*; decide whether this app follows appspec's rules.
- [ ] **Authorisation: field level.** Columns as keys in the same role map (`risk.owner: [read]`): no `read` hides the field everywhere (list, search, form, API); `read` without `update` makes it read-only; `create` without `update` is "set once, then locked". Most specific key wins: column, table, TableGroup, `"*"`. Warn at startup when a role can create records but not write a `not null` column without a default. Hiding for tidiness rather than security is layout, not access: an optional `screens:` section later, only if a real case needs it. (Row-level rules are out of scope, see Scope.)
- [ ] **Menus and submenus.** Collapsible `TableGroup` headings are done. Next, if needed, a `menu` section in the companion file for nested groups, ordering, hiding lookup tables and non-table items (scorecards, reports, links). Hide tables the user's role cannot read.
- [ ] **Audit trail** — who changed what and when, in a separate audit table so the dbml stays a mirror of the data. Needs authentication first.
- [ ] **CSV import and export** — bulk-loading (e.g. the ~650 framework clauses in `../cyber-metrics/99-templates/framework.csv`) and bulk-editing.
- [ ] **DBML conformance suite.** Add the official DBML repository's parser test fixtures (check the licence first) and, in development only, compare our parser's output with `@dbml/core` (Node needed for development, never for users). Track the pass rate here.
- [ ] **Use more of what the parser already reads:** `check` / `checks` as `CHECK` constraints, `default:` in the DDL, `update:` actions, `increment`, optional relationships, schemas.
- [ ] **Metrics model (`test.dbml`) questions:** should risks have a domain; should controls map to framework clauses (`Ref: control.id <> framework_reference.id`); generate all framework clauses into `records`.
- [ ] **Postgres and deployment** (flask-deploy) once this is more than a prototype.
- [ ] **Optimistic locking** so two people editing the same record do not silently overwrite each other.
- [ ] **JSON/REST API with OpenAPI** generated from the dbml, over the existing `records.py`, so the same model gives a front-end team a backend. After authentication.
- [ ] **Export a standalone app** (larger, optional): generate a standalone Flask project from the dbml, so a prototype can grow into a real app without staying tied to the generator.
- [ ] **Custom SQL actions** (idea, design not started): a button on a record (e.g. "Move to the next department") that runs SQL defined next to the dbml. The one sanctioned way in for business logic; revisit after the DBML side is solid.
- [ ] **Hot reload:** watch the dbml file and re-parse / re-sync without a restart (needs the schema change work below to be safe).
- [ ] **`check` command:** parse the file and list everything that would be skipped or warned about, without starting the server (for CI and a fast "will my file work?").
- [ ] **`reset` / `reseed` command:** `records` are only loaded when a table is first created; prototyping needs "wipe and reload the sample data".
- [ ] **Packaging:** pip-installable (`dbml-app serve model.dbml`), possibly a Docker image, so using it does not mean cloning the repo.
- [ ] **Schema changes: silent drift (bug).** `crud/sync.py` only compares column names and SQLite types, so changes to enum values (the `CHECK`), `not null`, `unique`, refs and `delete:` actions never reach an existing database; indexes are created `IF NOT EXISTS` by name, so changing an index's columns does nothing. The database then no longer enforces what the dbml says.
- [ ] **Schema changes: `plan` / `migrate`.** Show the full difference between the dbml and the database (constraints included), then apply it with SQLite's table rebuild (create new, copy, swap), backing up the database file first. Today every destructive change stops startup with no way forward but deleting the database. Renames are the hard part: DBML has no rename syntax, so ask or take a hint.
