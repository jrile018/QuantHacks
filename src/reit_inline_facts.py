"""Offline, bounded monetary-fact adapter; not a conforming XBRL processor.

Unsupported transformations and malformed contexts are retained for review.
No taxonomy, DTD, network, model or OCR is loaded by this module.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation, localcontext
from io import BytesIO
import json
import re
import xml.etree.ElementTree as ET

X = 'http://www.xbrl.org/2003/instance'
IX = {'http://www.xbrl.org/2013/inlineXBRL', 'http://www.xbrl.org/2008/inlineXBRL'}
D = 'http://xbrl.org/2006/xbrldi'
XSI = 'http://www.w3.org/2001/XMLSchema-instance'
MAX_BYTES = 25 * 1024 * 1024
MAX_FACTS = 100000
MAX_XML_DEPTH = 256
MAX_XML_ELEMENTS = 250000
MAX_NAMESPACE_BINDINGS = 128
TRANSFORMS = {
    'http://www.xbrl.org/inlineXBRL/transformation/2015-02-26': {'numdotdecimal': 'dot', 'numcommadecimal': 'comma', 'zerodash': 'zero_dash'},
    'http://www.xbrl.org/inlineXBRL/transformation/2020-02-12': {'num-dot-decimal': 'dot', 'num-comma-decimal': 'comma', 'fixed-zero': 'zero'},
    'http://www.xbrl.org/inlineXBRL/transformation/2022-02-16': {'num-dot-decimal': 'dot', 'num-comma-decimal': 'comma', 'fixed-zero': 'zero'},
}


def _qname(value, namespaces):
    value = (value or '').strip()
    pieces = value.split(':')
    if len(pieces) == 2 and all(re.fullmatch(r'[A-Za-z_][\w.-]*', p) for p in pieces):
        prefix, name = pieces
        if prefix in namespaces:
            return namespaces[prefix], name
    elif len(pieces) == 1 and re.fullmatch(r'[A-Za-z_][\w.-]*', value):
        return namespaces.get('', ''), value
    raise ValueError('unresolved_qname')


def _expanded(value, namespaces):
    namespace, local = _qname(value, namespaces)
    return '{' + namespace + '}' + local


def _date(value):
    if not value or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value.strip()):
        raise ValueError('invalid_context_period')
    return date.fromisoformat(value.strip()).isoformat()


def _context(element, scopes):
    flags = []
    entity = element.find(f'{{{X}}}entity')
    identifiers = [] if entity is None else entity.findall(f'{{{X}}}identifier')
    result = {'entity_identifier': None, 'entity_scheme': None, 'period_type': None,
              'period_start': None, 'period_end': None, 'as_of_date': None, 'dimensions': []}
    if len(identifiers) != 1 or not (identifiers[0].text or '').strip() or not identifiers[0].get('scheme'):
        flags.append('invalid_context_entity')
    else:
        result.update(entity_identifier=identifiers[0].text.strip(), entity_scheme=identifiers[0].get('scheme'))
    periods = element.findall(f'{{{X}}}period')
    try:
        if len(periods) != 1:
            raise ValueError('invalid_context_period')
        children = list(periods[0])
        tags = [e.tag for e in children]
        if tags == [f'{{{X}}}instant']:
            result.update(period_type='instant', as_of_date=_date(children[0].text))
        elif tags == [f'{{{X}}}startDate', f'{{{X}}}endDate']:
            start, end = map(lambda e: _date(e.text), children)
            if start > end:
                raise ValueError('invalid_context_period')
            result.update(period_type='duration', period_start=start, period_end=end)
        else:
            raise ValueError('invalid_context_period')
    except (ValueError, TypeError):
        flags.append('invalid_context_period')
    axes = set()
    for container in element.iter():
        if container.tag not in {f'{{{X}}}segment', f'{{{X}}}scenario'}:
            continue
        for member in container:
            try:
                axis = _expanded(member.get('dimension'), scopes[id(member)])
                if axis in axes:
                    flags.append('duplicate_context_dimension')
                axes.add(axis)
                if member.tag == f'{{{D}}}explicitMember':
                    result['dimensions'].append({'axis': axis, 'member': _expanded(member.text, scopes[id(member)])})
                elif member.tag == f'{{{D}}}typedMember' and len(member) == 1:
                    result['dimensions'].append({'axis': axis, 'typed_value': ET.tostring(member[0], encoding='unicode')})
                    flags.append('typed_dimension_semantics_unverified')
                else:
                    flags.append('unsupported_context_content')
            except ValueError:
                flags.append('unresolved_context_dimension')
    result['dimensions'].sort(key=lambda d: json.dumps(d, sort_keys=True))
    return result, flags


def _visible_text(element):
    parts, stack, length = [], [('node', element)], 0
    excluded = {f'{{{ns}}}exclude' for ns in IX}
    while stack:
        kind, value = stack.pop()
        if kind == 'text':
            text = value or ''
            parts.append(text[:max(0, 201 - length)])
            length += len(text)
            if length > 200:
                return ''.join(parts), True
        elif value.tag not in excluded:
            for child in reversed(list(value)):
                stack.append(('text', child.tail))
                stack.append(('node', child))
            stack.append(('text', value.text))
    return ''.join(parts), False


def _numeric(element, namespaces, inline):
    visible, overflow = _visible_text(element)
    text = visible.strip()
    flags = ['numeric_text_limit'] if overflow else []
    nil_value = element.get(f'{{{XSI}}}nil')
    nil = nil_value in {'true', '1'}
    if nil_value not in {None, 'true', '1', 'false', '0'}:
        flags.append('invalid_nil_attribute')
    precision = element.get('decimals')
    if precision is not None and precision != 'INF' and not re.fullmatch(r'[+-]?\d{1,2}', precision):
        flags.append('invalid_decimals')
    elif precision not in {None, 'INF'} and not -20 <= int(precision) <= 20:
        flags.append('unsupported_decimals_range')
    if element.get('precision') is not None:
        flags.append('unsupported_precision_attribute')
    if nil:
        if text:
            flags.append('nil_with_content')
        return None, True, text, flags
    if overflow:
        return None, False, text, flags
    try:
        if len(text) > 200:
            raise ValueError('numeric_text_limit')
        value_text = text
        if inline and element.get('format'):
            uri, local = _qname(element.get('format'), namespaces)
            mode = TRANSFORMS.get(uri, {}).get(local)
            if mode is None:
                raise ValueError('unsupported_numeric_transform')
            if mode in {'zero', 'zero_dash'}:
                if mode == 'zero_dash' and text not in {'-', '—', '–'}:
                    raise ValueError('unsupported_numeric_lexical_value')
                value_text = '0'
            elif mode == 'dot':
                if not re.fullmatch(r'[, \u00a00-9]*(\.[ \u00a00-9]+)?', text) or not re.search(r'[0-9]', text):
                    raise ValueError('unsupported_numeric_lexical_value')
                value_text = re.sub(r'[, \u00a0]', '', text)
            elif mode == 'comma':
                if not re.fullmatch(r'[. \u00a00-9]*(,[ \u00a00-9]+)?', text) or not re.search(r'[0-9]', text):
                    raise ValueError('unsupported_numeric_lexical_value')
                value_text = re.sub(r'[. \u00a0]', '', text).replace(',', '.')
        elif not re.fullmatch(r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)', text):
            raise ValueError('unsupported_numeric_lexical_value')
        scale = element.get('scale', '0') if inline else '0'
        if not re.fullmatch(r'[+-]?\d{1,2}', scale) or not -20 <= int(scale) <= 20:
            raise ValueError('unsupported_scale')
        sign = element.get('sign') if inline else None
        if sign not in {None, '-'}:
            raise ValueError('invalid_sign')
        with localcontext() as ctx:
            ctx.prec = 250
            value = Decimal(value_text) * Decimal(10) ** int(scale)
            if sign == '-':
                value = -value
        if not value.is_finite():
            raise ValueError('nonfinite_numeric_value')
        return format(value, 'f'), False, text, flags
    except (ValueError, InvalidOperation) as exc:
        flags.append(str(exc) if isinstance(exc, ValueError) else 'invalid_numeric_value')
        return None, False, text, flags


def extract_inline_facts(raw: bytes) -> dict:
    """Read well-formed XHTML/Inline XBRL or an extracted XBRL instance.

    Original untagged HTML is handled separately by reit_tables. An XML parse
    failure never turns visible numbers into guessed XBRL values.
    """
    if len(raw) > MAX_BYTES or re.search(br'<!ENTITY\b', raw, re.I):
        return {'facts': [], 'issues': ['xml_resource_or_entity_declaration_limit']}
    scopes, stack, pending, element_count = {}, [], [], 0
    try:
        iterator = ET.iterparse(BytesIO(raw), events=('start-ns', 'start', 'end'))
        for event, node in iterator:
            if event == 'start-ns':
                pending.append(node)
            elif event == 'start':
                element_count += 1
                if len(stack) >= MAX_XML_DEPTH:
                    return {'facts': [], 'issues': ['xml_depth_limit']}
                if element_count > MAX_XML_ELEMENTS:
                    return {'facts': [], 'issues': ['xml_element_limit']}
                ns = stack[-1] if stack else {}
                if pending:
                    ns = dict(ns)
                    ns.update(pending)
                if len(ns) > MAX_NAMESPACE_BINDINGS:
                    return {'facts': [], 'issues': ['xml_namespace_limit']}
                pending.clear()
                scopes[id(node)] = ns
                stack.append(ns)
            else:
                stack.pop()
        root = iterator.root
    except (ET.ParseError, ValueError):
        return {'facts': [], 'issues': ['xml_parse_failed']}
    context_nodes, unit_nodes = defaultdict(list), defaultdict(list)
    issues = []
    for node in root.iter():
        if node.tag == f'{{{X}}}context':
            if node.get('id') and node.get('id') == node.get('id').strip():
                context_nodes[node.get('id')].append(node)
            else:
                issues.append('context_definition_missing_or_invalid_id')
        elif node.tag == f'{{{X}}}unit':
            if node.get('id') and node.get('id') == node.get('id').strip():
                unit_nodes[node.get('id')].append(node)
            else:
                issues.append('unit_definition_missing_or_invalid_id')
    contexts = {key: _context(nodes[0], scopes) for key, nodes in context_nodes.items() if len(nodes) == 1}
    units = {}
    for key, nodes in unit_nodes.items():
        if len(nodes) != 1:
            continue
        measures = list(nodes[0])
        try:
            if len(measures) != 1 or measures[0].tag != f'{{{X}}}measure':
                raise ValueError('unsupported_unit')
            units[key] = _expanded(measures[0].text, scopes[id(measures[0])])
        except ValueError:
            pass
    facts = []
    hidden_nodes = {id(n) for hidden in root.iter() if hidden.tag in {f'{{{ns}}}hidden' for ns in IX} for n in hidden.iter()}
    for index, node in enumerate(root.iter()):
        inline = node.tag in {f'{{{ns}}}nonFraction' for ns in IX}
        fraction = node.tag in {f'{{{ns}}}fraction' for ns in IX}
        instance = node.get('contextRef') is not None and not node.tag.startswith(tuple('{' + ns + '}' for ns in IX))
        if not (inline or instance or fraction):
            continue
        if len(facts) >= MAX_FACTS:
            issues.append('fact_count_limit')
            break
        flags = []
        context_id, unit_id = node.get('contextRef'), node.get('unitRef')
        if not context_id:
            flags.append('missing_context_reference')
        if not unit_id:
            flags.append('missing_unit_reference')
        context, context_flags = contexts.get(context_id, ({}, ['ambiguous_context_id' if len(context_nodes.get(context_id, [])) > 1 else 'unresolved_context']))
        flags.extend(context_flags)
        namespace, name = None, None
        try:
            if inline or fraction:
                namespace, name = _qname(node.get('name'), scopes[id(node)])
            elif node.tag.startswith('{'):
                namespace, name = node.tag[1:].split('}', 1)
            else:
                raise ValueError('unresolved_concept')
        except ValueError as exc:
            flags.append(str(exc))
        measure = units.get(unit_id)
        if not measure:
            flags.append('unsupported_or_unresolved_unit')
        value, nil, text, numeric_flags = _numeric(node, scopes[id(node)], inline)
        flags.extend(numeric_flags)
        if fraction:
            flags.append('unsupported_fraction')
            value = None
        if node.get('target') is not None:
            flags.append('unsupported_target')
        if node.get('continuedAt') is not None:
            flags.append('unsupported_numeric_continuation')
        facts.append({**context, 'context_id': context_id, 'unit_id': unit_id, 'unit_measure': measure,
                      'concept_namespace': namespace, 'concept_local_name': name, 'value': value,
                      'is_nil': nil, 'decimals': node.get('decimals'), 'raw_text': text,
                      'hidden': id(node) in hidden_nodes, 'quality_flags': sorted(set(flags)),
                      'evidence': {'locator_type': 'xml_element', 'element_id': node.get('id'),
                                   'element_index': index, 'quoted_text': text}})
    return {'facts': facts, 'issues': issues}
