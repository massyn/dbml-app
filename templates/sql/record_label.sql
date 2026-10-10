SELECT {{ table.display_column.name|ident }} AS label
FROM {{ table.name|ident }}
WHERE {{ table.pk.name|ident }} = ?
