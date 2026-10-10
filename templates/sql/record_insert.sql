INSERT INTO {{ table.name|ident }} ({% for c in columns %}{{ c|ident }}{% if not loop.last %}, {% endif %}{% endfor %})
VALUES ({% for c in columns %}?{% if not loop.last %}, {% endif %}{% endfor %})
