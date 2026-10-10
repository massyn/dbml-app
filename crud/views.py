"""CRUD routes for every table in the DBML schema.

Each view renders a full page, or — with ?modal=1 — a fragment for the picker modal,
in which case writes answer with JSON instead of redirecting.
"""

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)

from . import get_schema, links, records
from .forms import editable_columns, parse_form, parse_links
from .labels import label
from .model import Schema, Table
from .records import RecordError

bp = Blueprint("crud", __name__)


def _schema() -> Schema:
    return get_schema(current_app)


def _table(name: str) -> Table:
    try:
        return _schema().table(name)
    except KeyError:
        abort(404)


def _modal() -> bool:
    return request.args.get("modal") == "1"


@bp.get("/")
def index():
    schema = _schema()
    counts = {name: records.count(t) for name, t in schema.tables.items()}
    return render_template(
        "index.html", groups=schema.nav_groups, counts=counts, notes=schema.notes
    )


@bp.get("/t/<name>")
def list_records(name: str):
    table = _table(name)
    page = records.list_records(
        _schema(),
        table,
        search=request.args.get("q", ""),
        sort=request.args.get("sort", ""),
        direction=request.args.get("dir", "asc"),
        page=request.args.get("page", 1, type=int),
        page_size=current_app.config["PAGE_SIZE"],
    )
    template = "_list.html" if _modal() else "list.html"
    return render_template(template, table=table, page=page, modal=_modal())


def _form(table: Table, pk: str | None):
    creating = pk is None
    row = None
    if not creating:
        row = records.get_record(table, pk)
        if row is None:
            abort(404)

    errors: dict[str, str] = {}
    form_error = ""
    if request.method == "POST":
        values, errors = parse_form(table, request.form, creating)
        selected, link_errors = parse_links(_schema(), table, request.form)
        errors |= link_errors
        if not errors:
            try:
                saved_pk = records.save_record(table, values, pk, selected)
            except RecordError as exc:
                form_error = str(exc)
            else:
                if _modal():
                    return jsonify(
                        ok=True, id=saved_pk, label=records.label(table, saved_pk)
                    )
                flash(f"{label(table.name)} saved.", "success")
                return redirect(url_for("crud.list_records", name=table.name))
        shown = request.form.to_dict()
        chosen = links.labelled(_schema(), table, selected)
    elif creating:
        shown = {c.name: c.default for c in table.columns if c.default is not None}
        chosen = {link.field: [] for link in table.links}
    else:
        shown = row
        chosen = links.linked(_schema(), table, pk)

    context = {
        "table": table,
        "pk": pk,
        "values": shown,
        "labels": records.fk_labels(_schema(), table, shown),
        "columns": editable_columns(table, creating),
        "links": [(link, chosen[link.field]) for link in table.links],
        "errors": errors,
        "form_error": form_error,
        "modal": _modal(),
    }
    if _modal():
        if request.method == "POST":
            return jsonify(ok=False, html=render_template("_form.html", **context))
        return render_template("_form.html", **context)
    return render_template("form.html", **context)


@bp.route("/t/<name>/new", methods=["GET", "POST"])
def new_record(name: str):
    return _form(_table(name), None)


@bp.route("/t/<name>/<path:pk>/edit", methods=["GET", "POST"])
def edit_record(name: str, pk: str):
    return _form(_table(name), pk)


@bp.post("/t/<name>/<path:pk>/delete")
def delete_record(name: str, pk: str):
    table = _table(name)
    try:
        records.delete_record(_schema(), table, pk)
    except RecordError as exc:
        if _modal():
            return jsonify(ok=False, error=str(exc))
        flash(str(exc), "danger")
        return redirect(url_for("crud.edit_record", name=name, pk=pk))
    if _modal():
        return jsonify(ok=True)
    flash(f"{label(table.name)} deleted.", "success")
    return redirect(url_for("crud.list_records", name=name))
