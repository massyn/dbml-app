{# FROM / JOIN / WHERE shared by record_list.sql and record_count.sql.
   fks: [{column, table, target, display}]; filters: [column] each matched with = ? (all must match);
   search: [(alias, column)] matched with LIKE ? each (any may match). Parameters in that order. #}
{% macro from_where(table, fks, search, filters=[]) -%}
FROM {{ table.name|ident }} AS t
{% for fk in fks %}
LEFT JOIN {{ fk.table|ident }} AS j{{ loop.index }} ON j{{ loop.index }}.{{ fk.target|ident }} = t.{{ fk.column|ident }}
{% endfor %}
{% if filters or search %}
WHERE {% for col in filters %}t.{{ col|ident }} = ? AND {% endfor %}{% if search %}({% for alias, col in search %}{% if not loop.first %} OR {% endif %}CAST({{ alias }}.{{ col|ident }} AS TEXT) LIKE ?{% endfor %}){% else %}1{% endif %}

{% endif %}
{%- endmacro %}
