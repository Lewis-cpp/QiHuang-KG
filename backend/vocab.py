"""Versioned vocabularies that map AI query words to stored values (measured on build cbadd11e…)."""

# Query word → text.dynasty_zh values of the classics that formulas cite.
DYNASTY_V1 = {
    '汉': ('汉', '东汉', '战国至汉'), '宋': ('宋', '北宋', '南宋'),
    '唐': ('唐',), '金': ('金',), '元': ('元',), '明': ('明',), '清': ('清',), '民国': ('民国',),
    '近代': ('清末民初', '民国'), '现代': ('现代（中华人民共和国）',),
}
NATURE_V1 = {'温': 'warm', '寒': 'cold', '平': 'neutral', '凉': 'cool', '热': 'hot',
             '微寒': 'slightly_cold', '微温': 'slightly_warm', '大寒': 'very_cold'}
ROUTE_V1 = {'口服': 'Oral', '外用': 'Topical', '注射': 'Injection'}


def dynasty(value):
    """Stored dynasty values for a query word or a stored value itself; None outside the table."""
    if value in DYNASTY_V1:
        return DYNASTY_V1[value]
    return (value,) if any(value in values for values in DYNASTY_V1.values()) else None


def enum(table, value):
    """The stored English value for a Chinese or English term; None outside the table."""
    english = {stored.casefold(): stored for stored in table.values()}
    return table.get(value) or english.get(value.casefold())


def chinese(table, stored):
    return next(word for word, value in table.items() if value == stored)
