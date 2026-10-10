{# FROM / JOIN / WHERE shared by record_list.sql and record_count.sql.
   fks: [{column, table, target, display}]; search: [(alias, column)] matched with LIKE ? each. #}
{% macro from_where(table, fks, search) -%}
FROM {{ table.name|ident }} AS t
{% for fk in fks %}
LEFT JOIN {{ fk.table|ident }} AS j{{ loop.index }} ON j{{ loop.index }}.{{ fk.target|ident }} = t.{{ fk.column|ident }}
{% endfor %}
{% if search %}
WHERE {% for alias, col in search %}{% if not loop.first %} OR {% endif %}CAST({{ alias }}.{{ col|ident }} AS TEXT) LIKE ?{% endfor %}

{% endif %}
{%- endmacro %}
