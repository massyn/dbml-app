{% from '_record_filter.sql' import from_where %}
SELECT t.*
{% for fk in fks %}
    , j{{ loop.index }}.{{ fk.display|ident }} AS {{ ('__label_' ~ fk.column)|ident }}
{% endfor %}
{% for l in links %}
    , (SELECT GROUP_CONCAT(o.{{ l.display|ident }}, ', ')
       FROM {{ l.join_table|ident }} AS lj
       JOIN {{ l.other_table|ident }} AS o ON o.{{ l.other_pk|ident }} = lj.{{ l.other_column|ident }}
       WHERE lj.{{ l.self_column|ident }} = t.{{ table.pk.name|ident }}) AS {{ l.field|ident }}
{% endfor %}
{{ from_where(table, fks, search) }}
ORDER BY {{ sort[0] }}.{{ sort[1]|ident }} {{ direction }}
LIMIT ? OFFSET ?
