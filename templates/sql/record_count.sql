{% from '_record_filter.sql' import from_where %}
SELECT COUNT(*) AS n
{{ from_where(table, fks, search) }}
