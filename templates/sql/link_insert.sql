INSERT INTO {{ link.join_table|ident }} ({{ link.self_column|ident }}, {{ link.other_column|ident }})
VALUES (?, ?)
