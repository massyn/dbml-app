SELECT o.{{ other_pk|ident }} AS id, o.{{ display|ident }} AS label
FROM {{ link.join_table|ident }} AS lj
JOIN {{ link.other_table|ident }} AS o ON o.{{ other_pk|ident }} = lj.{{ link.other_column|ident }}
WHERE lj.{{ link.self_column|ident }} = ?
ORDER BY label
