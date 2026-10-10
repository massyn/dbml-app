{% from '_column.sql' import column_def %}
ALTER TABLE {{ table.name|ident }} ADD COLUMN {{ column_def(column) }}
