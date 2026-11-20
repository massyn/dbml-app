# dbml-app

Turn your DBML definition into an app.

Design your data model on [dbdiagram.io](https://dbdiagram.io), drop the DBML file in, and you get a working web app straight away: a menu entry for every table, searchable and sortable lists, forms to add and edit records, dropdowns for enums and pickers for linked records. It is a quick way to see what an app built on your model would look and feel like, before writing any code.

There are no conventions of our own to learn. The app renders what the DBML says and only fills in where the DBML is silent.

## From dbdiagram to app

1. **Design the model** on [dbdiagram.io](https://dbdiagram.io). Tables, columns, enums, relationships, notes and `TableGroup`s all carry through to the app.
2. **Save the DBML.** Copy the code from the dbdiagram editor into a file, e.g. `model.dbml`.
3. **Install** (Python 3.10 or later):

   ```sh
   pip install -q -r requirements.txt
   ```

4. **Run the app**, naming the DBML file and a SQLite database to keep the data in:

   ```sh
   python app.py --dbml model.dbml --db model.db
   ```

5. **Open** <http://127.0.0.1:5000>.

The database is created from the DBML on first start. Any `records` blocks in the DBML are loaded as sample data, so the app has something in it from the start.

## What you get

| In the DBML | In the app |
| --- | --- |
| `Project` name and note | App title, and an introduction on the home page |
| `Table` | Menu item, list page (search, sort, paging), new and edit forms, delete with confirmation |
| `TableGroup` | Collapsible sections in the menu and on the home page |
| Column types | Matching form inputs: numbers, dates, checkboxes, single-line or multi-line text |
| `Enum` | Dropdown, with value notes shown as hints |
| `ref: >`, `<`, `-` | A picker that opens the linked table in a modal, where you can search, select or add a record |
| `ref: <>` | Many-to-many links, shown as chips on both sides |
| `pk`, `unique`, `not null`, `varchar(n)` | Enforced, with friendly messages on the form |
| `delete:` actions | Passed to the database; a record that others depend on cannot be deleted |
| `note` | Shown as Markdown on pages, under form fields and as column tooltips |
| `records` | Loaded as sample data when a table is first created |

Names are kept exactly as written in the DBML. On screen they are shown as labels, so `order_number` appears as **Order Number**.

## Changing the model

Edit the DBML and restart the app. New tables, columns and indexes are added to the existing database. A change that could lose data or that the app cannot apply safely (a removed column, a changed type, and so on) stops start-up with an explanation instead of guessing. Delete the database file to start afresh.

If the DBML is invalid, the app stops with the line and column of the problem. If it is valid but uses something the app does not support yet, that part is skipped with a warning and the rest still renders. See `CLAUDE.md` for the full list of supported DBML features.

## Configuration

`--dbml` and `--db` are required. Instead of passing them on the command line, you can set them in a `.env` file (copy `.env.example`). Command-line arguments take precedence.

| Setting | Default | Purpose |
| --- | --- | --- |
| `DBML` | (required) | The DBML file |
| `DB` | (required) | The SQLite database file |
| `HOST` | `127.0.0.1` | Address to listen on |
| `PORT` | `5000` | Port to listen on |
| `PAGE_SIZE` | `25` | Rows per page in lists |
| `FLASK_DEBUG` | `0` | Flask debug mode |
| `SECRET_KEY` | random | Signs flash messages and CSRF tokens; set it so open forms survive a restart |

## Try it

`test.dbml` is a working example:

```sh
python app.py --dbml test.dbml --db test.db
```

## Status

This is a prototype to show the idea is feasible. There is no sign-in or access control yet, so run it locally and do not expose it to a network.

## Tests

```sh
pytest -q
```
