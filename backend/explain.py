"""M4b explanation: gather formula materials, generate cited sentences, validate and degrade (m4b-spec).

The model call stays outside services.relational(): gather() closes its read-only transaction first.
"""

import json
import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from backend import model_client, queries, services

EXPLAIN_PROMPT = 'explain_v1'
EXPLAIN_SYSTEM = (Path(__file__).parent / 'prompts' / f'{EXPLAIN_PROMPT}.md').read_text(encoding='utf-8')
HEADINGS = ('组成与配伍', '功用与主治', '出处', '说明')
MAX_SECTIONS = 4
MAX_SENTENCES = 20
MAX_SENTENCE_CHARS = 120
MAX_CITATIONS = 5
MAX_INSUFFICIENT = 5
MAX_INSUFFICIENT_CHARS = 60

ROLE_ZH = {'jun': '君', 'chen': '臣', 'zuo': '佐', 'shi': '使'}
KIND_ZH = {'attributes': '属性', 'composition': '组成', 'pattern': '关联证候', 'source': '出处'}
CLAUSE_SPLIT = re.compile(r'[，。；：！？,;:]')
# 为君/作臣 prefix or 君药/佐以 suffix; 使 in 使脾气健运 is a verb, not a marker (m4b-spec §6.2).
ROLE_MARKER = re.compile(r'(?<=[为作])[君臣佐使]{1,2}|[君臣佐使]{1,2}(?=[药以])')
# 数字+单位 and 汉字数字+单位; “两味药” has no leading number, so 两 alone is no dosage.
DOSAGE = re.compile(r'\d+(?:\.\d+)?\s*(?:g|克|钱|两|枚|片|pieces)|[一二三四五六七八九十百半两]+\s*(?:钱|两|枚|片|克)')


class SentenceOut(BaseModel):
    model_config = ConfigDict(extra='forbid')
    text: str
    citations: list[str] = Field(min_length=1)


class SectionOut(BaseModel):
    model_config = ConfigDict(extra='forbid')
    heading: str
    sentences: list[SentenceOut] = Field(min_length=1)


class OutputOut(BaseModel):
    """Only the shape is strict here; limits and heading values get their own Chinese reasons."""
    model_config = ConfigDict(extra='forbid')
    sections: list[SectionOut] = Field(min_length=1, max_length=MAX_SECTIONS)
    insufficient: list[str]


def material(ref, kind, text, evidence_ids, **extra):
    return dict(ref=ref, kind=kind, text=text, evidence_ids=evidence_ids, **extra)


def attributes_text(attributes):
    parts = []
    category, subcategory = attributes.get('category'), attributes.get('subcategory')
    if category:
        parts.append(f'分类：{category}（{subcategory}）' if subcategory else f'分类：{category}')
    principle = attributes.get('treatment_principle')
    if isinstance(principle, dict) and principle.get('zh'):
        parts.append(f'治法：{principle["zh"]}')
    for key, name in (('description_zh', '方剂说明'), ('preparation_zh', '制法与服法'), ('source_chapter', '出处篇章')):
        if attributes.get(key):
            parts.append(f'{name}：{attributes[key]}')
    return '；'.join(parts)


def composition_text(label, properties, role):
    parts = []
    if properties.get('dosage_raw'):
        parts.append(f'剂量 {properties["dosage_raw"]}')
    # No role character may appear for a missing or conflicting role, so the model cannot pick one up.
    parts.append(f'角色 {role}' if role else '角色：资料未给出或存在冲突')
    if properties.get('position') is not None:
        parts.append(f'位置 {properties["position"] + 1}')
    return f'{label}：' + '；'.join(parts)


def evidence_by_edge(c, edge_ids):
    grouped = {edge_id: [] for edge_id in edge_ids}
    if edge_ids:
        c.execute('SELECT id,edge_id FROM evidence WHERE edge_id=ANY(%s) ORDER BY id', (edge_ids,))
        for row in c.fetchall():
            grouped[row['edge_id']].append(row['id'])
    return grouped


def gather(entity_id, build_id=None):
    """Materials M1…Mn and the validation dictionaries, read in one relational context."""
    with services.relational(build_id) as c:
        build = queries.current_build(c)
        entity = queries.require_entity(c, entity_id)
        if entity['type'] != 'formula':
            raise services.ServiceError('unsupported_entity_type', '只有方剂支持生成 AI 解释')
        attributes = json.loads(entity['attributes_json'])
        materials = []

        c.execute('SELECT id FROM evidence WHERE entity_id=%s ORDER BY id', (entity_id,))
        materials.append(material('M1', 'attributes', attributes_text(attributes),
                                  [row['id'] for row in c.fetchall()]))

        c.execute("SELECT e.id AS edge_id, e.quality_state, e.properties_json AS e0_properties_json, "
                  'n.id AS n0_id, n.label AS n0_label FROM edge e JOIN entity n ON n.id=e.target_id '
                  "WHERE e.source_id=%s AND e.relation='CONTAINS'", (entity_id,))
        composition = [{**row, 'e0_properties': json.loads(row['e0_properties_json'])} for row in c.fetchall()]
        composition.sort(key=queries.position_key)
        c.execute("SELECT e.id AS edge_id, n.label FROM edge e JOIN entity n ON n.id=e.target_id "
                  "WHERE e.source_id=%s AND e.relation='ASSOCIATED_WITH_PATTERN' "
                  'ORDER BY n.label COLLATE "C", n.id', (entity_id,))
        patterns = c.fetchall()
        c.execute("SELECT e.id AS edge_id, n.label, n.attributes_json AS cited_attributes FROM edge e "
                  'JOIN entity n ON n.id=e.target_id WHERE e.source_id=%s AND e.relation=\'CITED_IN\' '
                  'ORDER BY n.label COLLATE "C", n.id', (entity_id,))
        sources = c.fetchall()

        edge_ids = [row['edge_id'] for row in composition] + [row['edge_id'] for row in patterns]
        edge_ids += [row['edge_id'] for row in sources]
        evidence = evidence_by_edge(c, edge_ids)
        for row in composition:
            properties = row['e0_properties']
            role = None if row['quality_state'] == 'conflicting' else ROLE_ZH.get(properties.get('role'))
            materials.append(material(
                f'M{len(materials) + 1}', 'composition',
                composition_text(row['n0_label'], properties, role), evidence[row['edge_id']],
                herb_id=row['n0_id'], herb=row['n0_label'], role=role,
                dosage_raw=properties.get('dosage_raw'), conflicting=row['quality_state'] == 'conflicting'))
        for row in patterns:
            materials.append(material(f'M{len(materials) + 1}', 'pattern', f'关联证候：{row["label"]}',
                                      evidence[row['edge_id']]))
        for row in sources:
            dynasty = json.loads(row['cited_attributes']).get('dynasty_zh')
            text = f'出处：《{row["label"]}》' + (f'，{dynasty}' if dynasty else '')
            materials.append(material(f'M{len(materials) + 1}', 'source', text, evidence[row['edge_id']]))

        herb_ids = [row['n0_id'] for row in composition]
        c.execute('SELECT entity_id,name FROM alias WHERE entity_id=ANY(%s)', (herb_ids,))
        herb_aliases = {}
        for row in c.fetchall():
            herb_aliases.setdefault(row['entity_id'], []).append(row['name'])
        # The lexicon is only usable inside this transaction; everything else is plain Python data.
        vocab = vocabularies(c, materials, composition, herb_aliases)

    return dict(entity_id=entity_id, label=entity['label'], build_id=build, materials=materials, **vocab)


def vocabularies(c, materials, composition, herb_aliases):
    """Name lexicon, formula names and the per-herb role/dosage maps used by validate()."""
    names = set()
    c.execute("SELECT label FROM entity WHERE type='herb'")
    names.update(row['label'] for row in c.fetchall())
    c.execute("SELECT label FROM entity WHERE type='herbal_piece' AND length(label) >= 2")
    names.update(row['label'] for row in c.fetchall())
    c.execute('SELECT DISTINCT a.name FROM alias a JOIN entity e ON e.id=a.entity_id '
              "WHERE e.type IN ('herb','herbal_piece') AND length(a.name) >= 2")
    names.update(row['name'] for row in c.fetchall())
    c.execute("SELECT label FROM entity WHERE type='formula'")
    formula_names = sorted((row['label'] for row in c.fetchall()), key=len, reverse=True)
    lexicon = build_lexicon(names)

    name_info, allowed = {}, set()
    for row in composition:
        label = row['n0_label']
        role = None if row['quality_state'] == 'conflicting' else ROLE_ZH.get(row['e0_properties'].get('role'))
        dosage = normalize_dosage(row['e0_properties'].get('dosage_raw') or '')
        info = dict(role=role, dosage=dosage or None)
        for name in [label] + [n for n in herb_aliases.get(row['n0_id'], []) if len(n) >= 2]:
            name_info[name] = info
            allowed.add(name)
    # A dictionary name that appears verbatim in any material text is source-supported (m4b-spec §6.2).
    for item in materials:
        allowed.update(name for _, name in scan_names(item['text'], lexicon))
    return dict(lexicon=lexicon, formula_names=formula_names, allowed=allowed, name_info=name_info,
                formula_dosages={info['dosage'] for info in name_info.values() if info['dosage']})


def build_lexicon(names):
    """First character → names longest first, so 熟地黄 is found before 地黄."""
    lexicon = {}
    for name in names:
        lexicon.setdefault(name[0], []).append(name)
    return {first: sorted(bucket, key=len, reverse=True) for first, bucket in lexicon.items()}


def scan_names(text, lexicon):
    """Longest-match-first, non-overlapping dictionary names as (start, name)."""
    found, i = [], 0
    while i < len(text):
        for name in lexicon.get(text[i], ()):
            if text.startswith(name, i):
                found.append((i, name))
                i += len(name)
                break
        else:
            i += 1
    return found


def mask_formulas(text, formula_names):
    # Formula names are not herb mentions and carry no role claim (四君子汤, 炙甘草汤, 使君子).
    for name in formula_names:
        if name in text:
            text = text.replace(name, '□' * len(name))
    return text


def normalize_dosage(text):
    return ''.join(text.split()).replace('克', 'g')


def clauses(text):
    """(start, end) spans of the clauses split on commas and stops; 顿号 keeps 药名 in one clause."""
    start = 0
    for match in CLAUSE_SPLIT.finditer(text):
        if match.start() > start:
            yield start, match.start()
        start = match.end()
    if start < len(text):
        yield start, len(text)


def role_markers(text):
    markers = {}
    for match in ROLE_MARKER.finditer(text):
        markers[match.span()] = set(match.group())
    return [(start, end, chars) for (start, end), chars in markers.items()]


def nearest(span, candidates):
    """The closest span by the characters between them; ties go to the later one (m4b-spec §6.2)."""
    start, end = span[0], span[1]
    best = None
    for candidate in candidates:
        gap = candidate[0] - end if candidate[0] >= end else start - candidate[1]
        if best is None or gap < best[0] or (gap == best[0] and candidate[0] > best[1][0]):
            best = (gap, candidate)
    return best[1]


def structure_reasons(output, bundle):
    """Shape, limits and citation membership (m4b-spec §5); content checks need a parseable structure."""
    try:
        parsed = OutputOut.model_validate(output)
    except ValidationError as error:
        detail = '；'.join(f"{'.'.join(map(str, item['loc'])) or '顶层'}：{item['msg']}" for item in error.errors())
        return [f'输出结构不符合约定：{detail}'], None
    refs = {m['ref'] for m in bundle['materials']}
    problems = []
    headings = [section.heading for section in parsed.sections]
    if len(set(headings)) != len(headings):
        problems.append(f'输出结构不符合约定：heading 重复，只能是 {"、".join(HEADINGS)} 各一次')
    for heading in headings:
        if heading not in HEADINGS:
            problems.append(f'输出结构不符合约定：heading“{heading}”只能是 {"、".join(HEADINGS)} 之一')
    total = sum(len(section.sentences) for section in parsed.sections)
    if total > MAX_SENTENCES:
        problems.append(f'输出结构不符合约定：句子总数 {total} 超过 {MAX_SENTENCES}')
    index = 0
    for section in parsed.sections:
        for sentence in section.sentences:
            index += 1
            if not 1 <= len(sentence.text.strip()) <= MAX_SENTENCE_CHARS:
                problems.append(f'输出结构不符合约定：第 {index} 句的字数必须在 1 到 {MAX_SENTENCE_CHARS} 之间')
            unknown = [ref for ref in dict.fromkeys(sentence.citations) if ref not in refs]
            if unknown:
                problems.append(f'第 {index} 句的引用 {("、".join(unknown))} 不在本次材料中')
            if len(set(sentence.citations)) > MAX_CITATIONS:
                problems.append(f'输出结构不符合约定：第 {index} 句的引用超过 {MAX_CITATIONS} 个')
    if len(parsed.insufficient) > MAX_INSUFFICIENT:
        problems.append(f'输出结构不符合约定：insufficient 超过 {MAX_INSUFFICIENT} 条')
    for i, note in enumerate(parsed.insufficient, 1):
        if not 1 <= len(note.strip()) <= MAX_INSUFFICIENT_CHARS:
            problems.append(f'输出结构不符合约定：insufficient 第 {i} 条的字数必须在 1 到 {MAX_INSUFFICIENT_CHARS} 之间')
    return problems, parsed


def content_reasons(parsed, bundle):
    problems = []
    index = 0
    for section in parsed.sections:
        for sentence in section.sentences:
            index += 1
            problems += sentence_problems(f'第 {index} 句', sentence.text, bundle)
    for i, note in enumerate(parsed.insufficient, 1):
        problems += sentence_problems(f'资料不足第 {i} 条', note, bundle)
    return problems


def sentence_problems(where, text, bundle):
    problems = []
    masked = mask_formulas(text, bundle['formula_names'])
    occurrences = [(start, start + len(name), name) for start, name in scan_names(masked, bundle['lexicon'])]
    for _, _, name in occurrences:
        if name not in bundle['allowed']:
            problems.append(f'{where}提到的“{name}”不在本方材料中')
    problems += role_problems(where, masked, occurrences, bundle)
    problems += dosage_problems(where, masked, occurrences, bundle)
    return problems


def role_problems(where, masked, occurrences, bundle):
    markers = role_markers(masked)
    if not markers:
        return []
    problems = []
    for start, end in clauses(masked):
        here = [marker for marker in markers if start <= marker[0] and marker[1] <= end]
        if not here:
            # A clause without any marker makes no role claim, whatever herbs it mentions.
            continue
        for occ_start, occ_end, name in occurrences:
            if not (start <= occ_start and occ_end <= end) or name not in bundle['name_info']:
                continue
            role = bundle['name_info'][name]['role']
            if role is None:
                chars = ''.join(sorted(nearest((occ_start, occ_end), here)[2]))
                problems.append(f'{where}把“{name}”写成了{chars}，但材料中它的角色未给出或存在冲突')
            else:
                marker = nearest((occ_start, occ_end), here)
                if role not in marker[2]:
                    chars = ''.join(sorted(marker[2]))
                    problems.append(f'{where}把“{name}”写成了{chars}，但材料中它的角色是{role}')
    return problems


def dosage_problems(where, masked, occurrences, bundle):
    problems = []
    for match in DOSAGE.finditer(masked):
        word = normalize_dosage(match.group())
        start, end = clauses_of(match.start(), match.end(), masked)
        herbs = [occ for occ in occurrences
                 if start <= occ[0] and occ[1] <= end and occ[2] in bundle['name_info']]
        if herbs:
            name = nearest((match.start(), match.end()), herbs)[2]
            expected = bundle['name_info'][name]['dosage']
            if word != expected:
                problems.append(f'{where}的剂量“{match.group().strip()}”与材料中{name}的剂量不符')
        elif word not in bundle['formula_dosages']:
            problems.append(f'{where}的剂量“{match.group().strip()}”与本方材料中的剂量不符')
    return problems


def clauses_of(start, end, text):
    """The clause span that contains [start, end)."""
    for c_start, c_end in clauses(text):
        if c_start <= start and end <= c_end:
            return c_start, c_end
    return start, end


def validate(output, bundle):
    """All failure reasons at once, so the retry can show the model everything (m4b-spec §6)."""
    reasons, parsed = structure_reasons(output, bundle)
    if reasons or parsed is None:
        return reasons
    return content_reasons(parsed, bundle)


def user_content(bundle, failures=None):
    lines = ['<materials>']
    for item in bundle['materials']:
        # Newlines cannot break the one-line-per-material layout; the closing marker stays unique.
        text = item['text'].replace('\r', ' ').replace('\n', ' ')
        text = text.replace('<materials>', '').replace('</materials>', '')
        lines.append(f'[{item["ref"]}] {KIND_ZH[item["kind"]]}：{text}')
    lines.append('</materials>')
    if failures:
        lines.append('')
        lines.append('上一次输出未通过校验：')
        lines.extend(f'- {reason}' for reason in failures)
        lines.append('请只依据材料修正，并重新输出完整 JSON。')
    return '\n'.join(lines)


def cited_sections(parsed, bundle):
    evidence = {item['ref']: item['evidence_ids'] for item in bundle['materials']}
    sections = []
    for section in parsed['sections']:
        sentences = []
        for sentence in section['sentences']:
            refs = list(dict.fromkeys(sentence['citations']))
            # Evidence IDs follow the refs' order; a ref with several IDs lists them all.
            citations = list(dict.fromkeys(eid for ref in refs for eid in evidence[ref]))
            sentences.append(dict(text=sentence['text'], refs=refs, citations=citations))
        sections.append(dict(heading=section['heading'], sentences=sentences))
    return sections


def explain(entity_id, build_id=None):
    """Gather, at most two generations, validate; two failures degrade with the full materials."""
    bundle = gather(entity_id, build_id)
    usage, model_name, failures, attempts = [], None, None, 0
    for attempt in (1, 2):
        attempts = attempt
        output, meta = model_client.complete_json(
            EXPLAIN_SYSTEM, user_content(bundle, failures),
            log=dict(endpoint='explain', prompt_version=EXPLAIN_PROMPT, question=entity_id, attempt=attempt))
        usage.append(meta['usage'])
        model_name = meta['model']
        failures = validate(output, bundle)
        if not failures:
            parsed = OutputOut.model_validate(output).model_dump()
            return dict(status='ok', entity_id=bundle['entity_id'], sections=cited_sections(parsed, bundle),
                        insufficient=parsed['insufficient'], materials=bundle['materials'], failure=None,
                        attempts=attempt, model=model_name, prompt_version=EXPLAIN_PROMPT, usage=usage,
                        build_id=bundle['build_id'])
        if attempt == 1:
            model_client.record(dict(
                endpoint='explain', prompt_version=EXPLAIN_PROMPT, question=entity_id, attempt=1,
                request_id=meta['request_id'], model=meta['model'], usage=None, elapsed_ms=None,
                status='validation_failed', failure=failures))
    return dict(status='explanation_unavailable', entity_id=bundle['entity_id'], sections=[], insufficient=[],
                materials=bundle['materials'], failure=failures, attempts=attempts, model=model_name,
                prompt_version=EXPLAIN_PROMPT, usage=usage, build_id=bundle['build_id'])
