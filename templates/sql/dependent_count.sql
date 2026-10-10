SELECT COUNT(*) AS n FROM {{ table|ident }} WHERE {{ column|ident }} = ?
