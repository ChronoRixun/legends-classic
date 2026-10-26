"""Shared bounded menu palette/style conversion. No source tables are copied wholesale."""
from __future__ import annotations

import copy
import math
import xml.etree.ElementTree as ET

COLOR_LIMIT, STYLE_LIMIT = 75, 32
COLOR_RESERVE, STYLE_RESERVE = 8, 4
COLOR_FIELDS = ('color_nofocus', 'color_focus', 'color_highlight', 'color_disabled')


def rgba(value):
    channels = tuple(float(v) for v in (value or '').split())
    if len(channels) != 4 or any(not math.isfinite(v) or not 0 <= v <= 1 for v in channels):
        raise ValueError('menu palette needs four finite colour channels in 0..1')
    return channels


def allocate(base_colors, base_styles, original_colors, requests, *,
             color_reserve=COLOR_RESERVE, style_reserve=STYLE_RESERVE):
    """Translate requested legacy styles, preserving existing IDs and unrelated PC styles.

    requests is an iterable of modern style attribute dictionaries whose colour values
    are indices in the original table. Legacy ``color`` becomes ``color_nofocus``.
    Reuse only exact (value AND pulse) matches. Allocate lowest unused IDs, in sorted
    source-index order. Return private copies or fail before the caller writes anything.
    Replacing a previously allocated named style is idempotent.
    """
    if not 0 <= color_reserve < COLOR_LIMIT or not 0 <= style_reserve < STYLE_LIMIT:
        raise ValueError('invalid menu table reserve')
    colors, styles = copy.deepcopy(base_colors), copy.deepcopy(base_styles)
    used = {}
    for e in colors:
        idx = int(e.get('id', '-1'))
        if not 0 <= idx < COLOR_LIMIT or idx in used:
            raise ValueError('PC palette has an invalid or duplicate colour ID')
        rgba(e.get('value'))
        if e.get('pulse'):
            rgba(e.get('pulse'))
        used[idx] = e
    names = [e.get('name') for e in styles]
    if any(not name for name in names) or len(set(names)) != len(names):
        raise ValueError('PC style table has empty or duplicate names')
    wanted = []
    for attrs in requests:
        a = dict(attrs)
        if not a.get('name') or a.get('font') not in ('medium', 'big', 'hud', 'digital'):
            raise ValueError('menu style needs a name and a native font index')
        if 'color' in a:
            a.setdefault('color_nofocus', a.pop('color'))
        for key in COLOR_FIELDS:
            if key not in a:
                a[key] = a.get('color_focus' if key == 'color_highlight' else 'color_nofocus')
            a[key] = int(a[key])
        wanted.append(a)
    requested_names = [a['name'] for a in wanted]
    if len(set(requested_names)) != len(requested_names):
        raise ValueError('duplicate requested menu style')
    source = list(original_colors)
    ids = {}
    for idx in sorted({a[k] for a in wanted for k in COLOR_FIELDS}):
        if not 0 <= idx < len(source):
            raise ValueError('original palette lacks a requested colour')
        entry = source[idx]
        signature = (rgba(entry.get('value')), rgba(entry.get('pulse')) if entry.get('pulse') else None)
        found = next((key for key, e in sorted(used.items())
                      if (rgba(e.get('value')), rgba(e.get('pulse')) if e.get('pulse') else None) == signature), None)
        if found is None:
            found = next((key for key in range(COLOR_LIMIT) if key not in used), None)
            if found is None:
                raise ValueError('no free native palette ID for classic menus')
            attrs = {'id': str(found), 'value': entry.get('value')}
            if entry.get('pulse'):
                attrs['pulse'] = entry.get('pulse')
            used[found] = ET.SubElement(colors, 'color', attrs)
        ids[idx] = str(found)
    for e in list(styles):
        if e.get('name') in requested_names:
            styles.remove(e)
    if len(colors) > COLOR_LIMIT - color_reserve or len(styles) + len(wanted) > STYLE_LIMIT - style_reserve:
        raise ValueError('classic menu allocation exceeds native table headroom')
    for a in wanted:
        for key in COLOR_FIELDS:
            a[key] = ids[a[key]]
        ET.SubElement(styles, 'style', {k: str(v) for k, v in a.items()})
    return colors, styles, ids


def text_style(name, *, font='medium', normal=0, focus=0, disabled=5, allow=False):
    return {'name': name, 'font': font, 'color_nofocus': normal, 'color_focus': focus,
            'color_highlight': focus, 'color_disabled': disabled,
            'allow_focus': str(allow).lower(), 'focus_time': '0'}
