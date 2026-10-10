SELECT * FROM {{ table.name|ident }} WHERE {{ table.pk.name|ident }} = ?
