{% macro column_def(c) -%}
{{ c.name|ident }} {{ c.sql_type }}
{%- if c.pk %} PRIMARY KEY{% endif %}
{%- if c.not_null or c.pk %} NOT NULL{% endif %}
{%- if c.unique and not c.pk %} UNIQUE{% endif %}
{%- if c.kind == 'enum' %} CHECK ({{ c.name|ident }} IN ({% for v in c.enum_values %}{{ v|literal }}{% if not loop.last %}, {% endif %}{% endfor %})){% endif %}
{%- if c.kind == 'boolean' %} CHECK ({{ c.name|ident }} IN (0, 1)){% endif %}
{%- if c.ref %} REFERENCES {{ c.ref.table|ident }} ({{ c.ref.column|ident }}) ON DELETE {{ c.ref.on_delete }}{% endif %}
{%- endmacro %}
