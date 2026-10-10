CREATE {% if index.unique %}UNIQUE {% endif %}INDEX IF NOT EXISTS {{ index.name|ident }}
ON {{ table.name|ident }} ({% for c in index.columns %}{{ c|ident }}{% if not loop.last %}, {% endif %}{% endfor %})
