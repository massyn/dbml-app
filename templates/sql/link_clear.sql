DELETE FROM {{ link.join_table|ident }} WHERE {{ link.self_column|ident }} = ?
