UPDATE {{ table.name|ident }}
SET {% for c in columns %}{{ c|ident }} = ?{% if not loop.last %}, {% endif %}{% endfor %}

WHERE {{ table.pk.name|ident }} = ?
