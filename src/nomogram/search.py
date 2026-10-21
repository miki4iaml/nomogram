# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Searching the catalog: one index of every entry, wildcards, links.

Every entry of a catalog (formulations, quantity kinds, references,
constants, notations, trade terms, scales, relations, cross-checks,
families, units) is indexed once, the first time a search needs it, and
the index is frozen. A search is a conjunction of terms and field
filters:

- a **term** is a shell-style wildcard pattern (``*``, ``?``, ``[...]``)
  matched against the **words** of an entry; every term must match a
  word;
- words are taken from the entry's names and texts, compared without case
  or accents; identifiers in CamelCase or with underscores are also split
  (``SaturationVapourPressureOverWater`` gives *saturation*, *vapour*,
  *pressure*, *over*, *water*), and kept whole (``itu_r_p453_es_water``);
- symbols are compared in a normal form: ``\\rho_{\\mathrm{v}}``,
  ``ρ_v``, ``rho_v`` and *rhô_v* are all ``rho_v``; Greek letters go by
  their names, in English or in French;
- a **field filter** (``kind=``, ``variable=``, ``source=``...) applies
  the same matching to one field; several words in a filter must all
  match within one value of the field (one variable, one kind).

The result is a :class:`Selection`, which can be searched again and
combined with others (``&``, ``|``, ``-``). Names are added to entries by
providers (identifiers, notations, labels, CF names, Greek letters...):
new providers enrich the results without changing how searches are
written.
"""

from __future__ import annotations

import dataclasses
import re
import unicodedata
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from typing import TYPE_CHECKING, Any, overload

if TYPE_CHECKING:
    from nomogram.catalog import Catalog
    from nomogram.model import Formulation, Variable

__all__ = [
    "FIELDS",
    "SECTIONS",
    "Entry",
    "Selection",
    "fold",
    "symbol_form",
    "words",
]

#: Sections of the index, in the order results are listed.
SECTIONS = (
    "formulations",
    "kinds",
    "references",
    "constants",
    "notations",
    "trade_terms",
    "scales",
    "relations",
    "cross_checks",
    "families",
    "units",
)

#: Field filters of :meth:`nomogram.catalog.Catalog.search`, and what each
#: matches.
FIELDS: Mapping[str, str] = {
    "key": "the key of the entry",
    "kind": (
        "the output kind of a formulation, or a quantity kind itself; with "
        "specializations=True (default), kinds specializing it as well"
    ),
    "output": "the output variable of a formulation: identifier, symbols, kind, description",
    "input": "an input variable of a formulation: identifier, symbols, kind, description",
    "variable": "any variable, coefficient or constant of a formulation",
    "symbol": "a symbol of a formulation, as written by a notation (see notation=)",
    "notation": "the notation of the symbols matched by symbol= (default: all notations)",
    "source": "a cited reference: key and authors",
    "equation": "the equation number of a citation, with source= in the same citation",
    "family": "the family the entry belongs to",
    "keyword": "a keyword of a formulation or a family",
}

# Greek letters by character, after case folding; variants and the micro
# sign (which NFKD turns into mu) go to the letter's name.
_GREEK = dict(
    zip(
        "αβγδεζηθικλμνξοπρστυφχψω",
        [
            "alpha",
            "beta",
            "gamma",
            "delta",
            "epsilon",
            "zeta",
            "eta",
            "theta",
            "iota",
            "kappa",
            "lambda",
            "mu",
            "nu",
            "xi",
            "omicron",
            "pi",
            "rho",
            "sigma",
            "tau",
            "upsilon",
            "phi",
            "chi",
            "psi",
            "omega",
        ],
        strict=True,
    )
) | {"ϕ": "phi", "ϑ": "theta", "ϱ": "rho", "ϵ": "epsilon", "ϖ": "pi"}
_GREEK_NAMES = frozenset(_GREEK.values())
# French names differing from the English ones once accents are dropped.
_FRENCH = {"chi": "khi", "khi": "chi", "xi": "ksi", "ksi": "xi"}

_LATEX_COMMAND = re.compile(r"\\([a-z]+)")
_WRAPPERS = re.compile(r"\\(?:mathrm|mathit|mathbf|mathsf|text|operatorname)\b")
_SEPARATORS = re.compile(r"[^\w.:'\-]+")
_INNER = re.compile(r"[._:'\-]+")
_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")


def fold(text: str) -> str:
    """Text without case or accents, LaTeX commands and Greek letters by name.

    ``"Équation"`` gives ``"equation"``, ``"\\rho"`` and ``"ρ"`` give
    ``"rho"``.
    """
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c)).casefold()
    text = _LATEX_COMMAND.sub(r"\1", text)
    return "".join(_GREEK.get(c, c) for c in text)


def symbol_form(tex: str) -> str:
    """The normal form of a symbol: ``\\rho_{\\mathrm{v}}`` gives ``rho_v``.

    Font commands and braces are dropped, Greek letters go by name,
    superscripts become subscripts and primes ``_prime``.
    """
    text = _WRAPPERS.sub("", tex)
    text = re.sub(r"[{}\s]", "", text).replace("^", "_").replace("'", "_prime")
    text = fold(text).replace("\\", "")
    return re.sub(r"_+", "_", text).strip("_")


def _aliases(word: str) -> set[str]:
    found = {word}
    if word.startswith("var") and word[3:] in _GREEK_NAMES:
        found.add(word[3:])
    if word in _FRENCH:
        found.add(_FRENCH[word])
    return found


def words(text: str) -> frozenset[str]:
    """The words of a text, as a search compares them.

    Each token is kept whole and also split at dots, underscores, colons,
    hyphens, apostrophes and CamelCase boundaries; everything is folded
    (:func:`fold`).
    """
    found: set[str] = set()
    for raw in _SEPARATORS.split(text):
        token = raw.strip(".:'-")
        if not token:
            continue
        found |= _aliases(fold(token))
        for part in _INNER.split(_CAMEL.sub(" ", token).replace(" ", "_")):
            if part:
                found |= _aliases(fold(part))
    return frozenset(found)


def _symbol_words(tex: str) -> frozenset[str]:
    form = symbol_form(tex)
    return words(form) | {form}


@dataclass(frozen=True)
class Entry:
    """An entry of the catalog, as a search finds it.

    Attributes
    ----------
    section : str
        Its section, one of :data:`SECTIONS`.
    key : str
        Its key in the section.
    label : str
        A short description, for display.
    value : object
        The entry itself (a :class:`~nomogram.model.Formulation`, a
        :class:`~nomogram.semantics.QuantityKind`...).
    """

    section: str
    key: str
    label: str
    value: Any = field(repr=False, compare=False)

    @property
    def ref(self) -> str:
        """``section.key``, the reference used by ``uses`` and ``used_by``."""
        return f"{self.section}.{self.key}"


@dataclass(frozen=True)
class _Record:
    entry: Entry
    text: frozenset[str]
    fields: Mapping[str, tuple[frozenset[str], ...]]
    kinds: tuple[str, ...] = ()
    citations: tuple[tuple[str, frozenset[str], str | None], ...] = ()
    symbols: tuple[tuple[str, frozenset[str]], ...] = ()


def _join(*parts: object) -> str:
    return " ".join(str(p) for p in parts if p)


def _matches_text(items: Iterable[Any]) -> str:
    """Local names of external links (``Q190200``, a QUDT name)."""
    return " ".join(m.target.rstrip("/").rsplit("/", 1)[-1] for m in items)


def _kind_text(catalog: Catalog, name: str) -> str:
    kind = catalog.kinds[name]
    return _join(name, kind.label, *kind.cf_standard_names)


@dataclass(frozen=True)
class _Index:
    records: tuple[_Record, ...]
    by_ref: Mapping[str, _Record]
    used_by: Mapping[str, tuple[str, ...]]
    descendants: Mapping[str, frozenset[str]]


def _symbols_of(
    catalog: Catalog, formulation: Formulation, identifier: str
) -> list[tuple[str, str]]:
    """(notation key, symbol) for an identifier, in every notation that has it."""
    found = {"default": identifier}
    for citation in formulation.citations:
        notation = citation.notation
        if notation is not None and identifier in notation.symbols:
            found[notation.key] = notation.symbols[identifier]
    for key, notation in catalog.notations.items():
        if identifier in notation.symbols:
            found[key] = notation.symbols[identifier]
    return list(found.items())


def _variable_words(
    catalog: Catalog, formulation: Formulation, variable: Variable
) -> frozenset[str]:
    found = words(_join(variable.description, _kind_text(catalog, variable.kind)))
    for _, tex in _symbols_of(catalog, formulation, variable.identifier):
        found |= _symbol_words(tex)
    return found


def _formulation(
    catalog: Catalog, key: str, f: Formulation, family: str | None
) -> _Record:
    references = [catalog.references[r] for r in f.references]
    text = _join(
        key,
        f.label,
        f.note,
        *f.keywords,
        family,
        catalog.families[family].label if family is not None else None,
        _kind_text(catalog, f.output.kind),
        *(_join(r.key, r.authors, r.title, r.year) for r in references),
        _matches_text(f.matches),
    )
    inputs = tuple(_variable_words(catalog, f, v) for v in f.inputs)
    output = _variable_words(catalog, f, f.output)
    others = tuple(
        frozenset().union(
            *(_symbol_words(t) for _, t in _symbols_of(catalog, f, c.identifier))
        )
        | words(_join(c.note))
        for c in f.coefficients
    ) + tuple(
        frozenset().union(
            *(_symbol_words(t) for _, t in _symbols_of(catalog, f, k.identifier))
        )
        | words(_join(k.key, k.description))
        for k in f.constants
    )
    symbols = tuple(
        (notation, _symbol_words(tex))
        for name in (
            f.output.identifier,
            *(v.identifier for v in f.inputs),
            *(c.identifier for c in f.coefficients),
            *(k.identifier for k in f.constants),
        )
        for notation, tex in _symbols_of(catalog, f, name)
    )
    citations = tuple(
        (
            c.reference,
            words(_join(c.reference, catalog.references[c.reference].authors)),
            c.equation,
        )
        for c in f.citations
    )
    return _Record(
        entry=Entry("formulations", key, f.label, f),
        text=words(text),
        fields={
            "output": (output,),
            "input": inputs,
            "variable": (output, *inputs, *others),
            "keyword": tuple(words(k) for k in f.keywords),
        },
        kinds=(f.output.kind,),
        citations=citations,
        symbols=symbols,
    )


def _sourced(
    catalog: Catalog, *references: str | None
) -> tuple[tuple[str, frozenset[str], None], ...]:
    found = []
    for r in references:
        if r is None:
            continue
        found.append((r, words(_join(r, catalog.references[r].authors)), None))
    return tuple(found)


def _records(catalog: Catalog) -> list[_Record]:
    from nomogram.semantics import semantic_catalog

    family_of = {
        f"{section}.{key}": name
        for name, family in catalog.families.items()
        for section, keys in family.contents.items()
        for key in keys
    }
    records = []
    for key, f in catalog.formulations.items():
        records.append(
            _formulation(catalog, key, f, family_of.get(f"formulations.{key}"))
        )
    for name, kind in catalog.kinds.items():
        text = _join(
            _kind_text(catalog, name), kind.origin, _matches_text(kind.matches)
        )
        if kind.iri:
            text = _join(text, kind.iri.rsplit("/", 1)[-1])
        records.append(
            _Record(
                Entry("kinds", name, kind.label, kind), words(text), {}, kinds=(name,)
            )
        )
    for key, r in catalog.references.items():
        text = _join(key, r.authors, r.title, r.year, r.container, r.doi, r.note)
        records.append(
            _Record(
                Entry("references", key, _join(r.authors, r.year, r.title), r),
                words(_join(text, _matches_text(r.matches))),
                {},
                citations=_sourced(catalog, key),
            )
        )
    for key, k in catalog.constants.items():
        records.append(
            _Record(
                Entry("constants", key, k.description, k),
                words(
                    _join(key, k.identifier, k.description, _matches_text(k.matches))
                ),
                {},
                citations=_sourced(catalog, k.reference),
            )
        )
    for key, n in catalog.notations.items():
        symbols = tuple((key, _symbol_words(tex)) for tex in n.symbols.values())
        text = _join(
            key, n.label, *n.symbols, *(symbol_form(t) for t in n.symbols.values())
        )
        records.append(
            _Record(
                Entry("notations", key, n.label, n),
                words(text),
                {},
                citations=_sourced(catalog, n.reference),
                symbols=symbols,
            )
        )
    for key, t in catalog.trade_terms.items():
        text = _join(
            key,
            t.term,
            t.language,
            *(
                _join(m.community, m.definition, _kind_text(catalog, m.kind))
                for m in t.meanings
            ),
            _matches_text(t.matches),
        )
        records.append(
            _Record(
                Entry("trade_terms", key, f"{t.term} ({t.language})", t),
                words(text),
                {},
                kinds=tuple(m.kind for m in t.meanings),
                citations=_sourced(
                    catalog, *(s for m in t.meanings for s in m.sources)
                ),
            )
        )
    for key, s in catalog.scales.items():
        records.append(
            _Record(
                Entry("scales", key, s.label, s),
                words(
                    _join(
                        key, s.label, s.symbol, s.note, *s.kinds, *s.cf_standard_names
                    )
                ),
                {},
                citations=_sourced(catalog, s.reference),
            )
        )
    for key, rel in catalog.relations.items():
        label = f"{rel.subject} {rel.kind.value} {rel.object}"
        records.append(
            _Record(
                Entry("relations", key, label, rel),
                words(_join(key, label, rel.note)),
                {},
                citations=_sourced(catalog, rel.citation),
            )
        )
    for key, check in catalog.cross_checks.items():
        label = f"{check.implementation} {check.version}"
        records.append(
            _Record(
                Entry("cross_checks", key, label, check),
                words(_join(key, label, check.note)),
                {},
            )
        )
    for name, family in catalog.families.items():
        records.append(
            _Record(
                Entry("families", name, family.label, family),
                words(
                    _join(
                        name,
                        family.label,
                        *family.keywords,
                        _matches_text(family.matches),
                    )
                ),
                {"keyword": tuple(words(k) for k in family.keywords)},
            )
        )
    for name, unit in semantic_catalog().units.items():
        text = _join(
            name,
            unit.label,
            unit.symbol,
            unit.ucum,
            unit.pint,
            _matches_text(unit.matches),
        )
        records.append(_Record(Entry("units", name, unit.label, unit), words(text), {}))
    return [
        dataclasses.replace(
            record,
            fields={
                **record.fields,
                "key": (words(record.entry.key),),
                **(
                    {"family": (words(family_of[record.entry.ref]),)}
                    if record.entry.ref in family_of
                    else {}
                ),
            },
        )
        for record in records
    ]


def index(catalog: Catalog) -> _Index:
    """Build the search index of a catalog (see :meth:`Catalog.search`)."""
    records = tuple(_records(catalog))
    by_ref = {r.entry.ref: r for r in records}
    used_by: dict[str, list[str]] = {}
    for ref, targets in catalog.links.items():
        for target in targets:
            used_by.setdefault(target, []).append(ref)
    parents = {name: kind.specialization_of for name, kind in catalog.kinds.items()}
    descendants: dict[str, set[str]] = {name: {name} for name in parents}
    for name, parent in parents.items():
        while parent is not None and parent in descendants:
            descendants[parent].add(name)
            parent = parents[parent]
    return _Index(
        records=records,
        by_ref=by_ref,
        used_by={k: tuple(v) for k, v in used_by.items()},
        descendants={k: frozenset(v) for k, v in descendants.items()},
    )


#: Fields whose patterns are read as symbols (braces and font commands
#: dropped): ``\rho_{\mathrm{v}}`` is ``rho_v``.
_SYMBOLIC = frozenset({"output", "input", "variable"})


def _terms(pattern: str, symbol: bool = False) -> list[str]:
    return [symbol_form(t) if symbol else fold(t) for t in pattern.split()]


def _all_match(terms: list[str], found: frozenset[str]) -> bool:
    return all(any(fnmatchcase(word, term) for word in found) for term in terms)


def _keep(
    record: _Record,
    terms: list[str],
    section: str | None,
    filters: Mapping[str, str],
    kinds: frozenset[str] | None,
) -> bool:
    if section is not None and not fnmatchcase(record.entry.section, section):
        return False
    if not _all_match(terms, record.text):
        return False
    if kinds is not None and not set(record.kinds) & kinds:
        return False
    for name, pattern in filters.items():
        if name in ("kind", "source", "equation", "symbol", "notation"):
            continue
        values = record.fields.get(name)
        wanted = _terms(pattern, symbol=name in _SYMBOLIC)
        if values is None or not any(_all_match(wanted, v) for v in values):
            return False
    if "source" in filters or "equation" in filters:
        source = _terms(filters.get("source", "*"))
        equation = fold(filters.get("equation", "*"))
        if not any(
            _all_match(source, found) and fnmatchcase(fold(eq or ""), equation)
            for _, found, eq in record.citations
        ):
            return False
    if "symbol" in filters or "notation" in filters:
        symbol = _terms(filters.get("symbol", "*"), symbol=True)
        notation = fold(filters.get("notation", "*"))
        if not any(
            fnmatchcase(fold(key), notation) and _all_match(symbol, found)
            for key, found in record.symbols
        ):
            return False
    return True


def search(
    catalog: Catalog,
    terms: Sequence[str],
    *,
    section: str | None = None,
    specializations: bool = True,
    filters: Mapping[str, str],
) -> Selection:
    """See :meth:`nomogram.catalog.Catalog.search`."""
    unknown = sorted(set(filters) - set(FIELDS))
    if unknown:
        msg = (
            f"unknown search field(s): {', '.join(unknown)}; known: {', '.join(FIELDS)}"
        )
        raise TypeError(msg)
    built = catalog._search_index
    kinds = None
    if "kind" in filters:
        wanted = _terms(filters["kind"])
        matched = {
            name
            for name in catalog.kinds
            if _all_match(wanted, words(name) | {fold(name)})
        }
        if specializations:
            matched = {d for name in matched for d in built.descendants[name]}
        kinds = frozenset(matched)
    folded = [t for term in terms for t in _terms(term)]
    chosen = tuple(
        r.entry
        for r in built.records
        if _keep(r, folded, fold(section) if section else None, filters, kinds)
    )
    return Selection(chosen, catalog)


def _ref(entry: str | Entry) -> str:
    return entry.ref if isinstance(entry, Entry) else entry


def uses(catalog: Catalog, entry: str | Entry) -> Selection:
    """See :meth:`nomogram.catalog.Catalog.uses`."""
    built = catalog._search_index
    ref = _ref(entry)
    if ref not in built.by_ref:
        msg = f"no entry {ref!r} (expected section.key)"
        raise KeyError(msg)
    targets = catalog.links.get(ref, ())
    return Selection(tuple(built.by_ref[t].entry for t in targets), catalog)


def used_by(catalog: Catalog, entry: str | Entry) -> Selection:
    """See :meth:`nomogram.catalog.Catalog.used_by`."""
    built = catalog._search_index
    ref = _ref(entry)
    if ref not in built.by_ref:
        msg = f"no entry {ref!r} (expected section.key)"
        raise KeyError(msg)
    return Selection(
        tuple(built.by_ref[s].entry for s in built.used_by.get(ref, ())), catalog
    )


@dataclass(frozen=True, eq=False)
class Selection(Sequence[Entry]):
    """Entries found by a search: searchable again, and combinable.

    ``a & b`` keeps the entries of ``a`` also in ``b``, ``a | b`` adds
    those of ``b``, ``a - b`` removes them; the selections must come
    from the same catalog. :attr:`formulations` gives the formulations,
    for :func:`nomogram.comparison.compare` or a plot. In a notebook, a
    selection displays itself as a table.

    Attributes
    ----------
    entries : tuple of Entry
        The entries, in the order of the catalog.
    catalog : Catalog
        The catalog searched.
    """

    entries: tuple[Entry, ...]
    catalog: Catalog = field(repr=False)

    @overload
    def __getitem__(self, index: int) -> Entry: ...
    @overload
    def __getitem__(self, index: slice) -> Selection: ...
    def __getitem__(self, index: int | slice) -> Entry | Selection:
        if isinstance(index, slice):
            return Selection(self.entries[index], self.catalog)
        return self.entries[index]

    def __len__(self) -> int:
        return len(self.entries)

    def __iter__(self) -> Iterator[Entry]:
        return iter(self.entries)

    def __contains__(self, item: object) -> bool:
        if isinstance(item, Entry | str):
            return _ref(item) in self.refs
        return False

    @property
    def refs(self) -> tuple[str, ...]:
        """``section.key`` of each entry."""
        return tuple(e.ref for e in self.entries)

    @property
    def formulations(self) -> tuple[Formulation, ...]:
        """The formulations among the entries."""
        return tuple(e.value for e in self.entries if e.section == "formulations")

    def search(self, *terms: str, **filters: Any) -> Selection:
        """Search again, within this selection."""
        found: Selection = self.catalog.search(*terms, **filters)
        return self & found

    def _other(self, other: object) -> Selection | None:
        if not isinstance(other, Selection):
            return None
        if other.catalog is not self.catalog:
            msg = "selections from different catalogs cannot be combined"
            raise ValueError(msg)
        return other

    def __and__(self, other: object) -> Selection:
        found = self._other(other)
        if found is None:
            return NotImplemented
        keep = set(found.refs)
        return Selection(tuple(e for e in self.entries if e.ref in keep), self.catalog)

    def __or__(self, other: object) -> Selection:
        found = self._other(other)
        if found is None:
            return NotImplemented
        seen = set(self.refs)
        added = tuple(e for e in found.entries if e.ref not in seen)
        return Selection(self.entries + added, self.catalog)

    def __sub__(self, other: object) -> Selection:
        found = self._other(other)
        if found is None:
            return NotImplemented
        drop = set(found.refs)
        return Selection(
            tuple(e for e in self.entries if e.ref not in drop), self.catalog
        )

    def __repr__(self) -> str:
        shown = ", ".join(self.refs[:5]) + (", ..." if len(self) > 5 else "")
        return f"Selection({len(self)} entries: {shown})"

    def to_markdown(self) -> str:
        """The entries as a Markdown table; formulations with their equations."""
        if self.entries and all(e.section == "formulations" for e in self.entries):
            from nomogram.display import table

            return table(self.formulations).to_markdown()
        lines = ["| Entry | Description |", "|---|---|"]
        lines += [f"| `{e.ref}` | {e.label.replace('|', '/')} |" for e in self.entries]
        return "\n".join(lines) + "\n"

    def _repr_markdown_(self) -> str:
        return self.to_markdown()
