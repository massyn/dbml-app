{% from '_record_filter.sql' import from_where %}
SELECT t.*
{% for fk in fks %}
    , j{{ loop.index }}.{{ fk.display|ident }} AS {{ ('__label_' ~ fk.column)|ident }}
{% endfor %}
{{ from_where(table, fks, search, filters) }}
ORDER BY {{ sort[0] }}.{{ sort[1]|ident }} {{ direction }}
LIMIT ? OFFSET ?
