{% from '_column.sql' import column_def %}
CREATE TABLE IF NOT EXISTS {{ table.name|ident }} (
{% for c in table.columns %}
    {{ column_def(c) }}{% if not loop.last or table.composite_key %},{% endif %}

{% endfor %}
{% if table.composite_key %}
    PRIMARY KEY ({% for c in table.composite_key %}{{ c|ident }}{% if not loop.last %}, {% endif %}{% endfor %})
{% endif %}
)
