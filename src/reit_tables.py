"""Bounded HTML table evidence extraction; no financial interpretation.

Offsets address Python string characters, including the opening and closing
cell/table tags when present. Malformed omitted tags end at the next structural
boundary and are flagged. The grid retains the first occupant on collisions.
"""

from html.parser import HTMLParser


MAX_TABLES = 500
MAX_TABLE_DEPTH = 50
MAX_CELLS = 10_000
MAX_ROWS = 10_000
MAX_COLUMNS = 200
MAX_SPAN = 200
MAX_TEXT = 1_000_000  # visible characters retained per table
MAX_CONTEXT = 500
MAX_DOCUMENT_GRID_SLOTS = 500_000
MAX_DOCUMENT_CELLS = 50_000
MAX_DOCUMENT_ROWS = 50_000
_BLOCKS = {'p', 'div', 'br', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'}
_SUPPRESSED = {'script', 'style', 'template'}


def _visible(parts):
    return ' '.join(''.join(parts).split())


class _Table:
    def __init__(self, table_id, start, context, budget):
        self.result = dict(table_id=table_id, caption='', context=context,
                           rows=[], grid=[], quality_flags=[],
                           char_start=start, char_end=start)
        self.row = None
        self.cell = None
        self.parts = []
        self.caption = None
        self.row_count = 0
        self.cell_count = 0
        self.text_count = 0
        self.column = 0
        self.budget = budget
        self.grid_width = 0
        self.grid_blocked = False

    def flag(self, name):
        if name not in self.result['quality_flags']:
            self.result['quality_flags'].append(name)

    def append(self, data):
        if self.cell is None and self.caption is None:
            return
        available = MAX_TEXT - self.text_count
        if len(data) > available:
            self.flag('text_limit')
        data = data[:available]
        self.text_count += len(data)
        if self.caption is not None:
            self.caption.append(data)
        elif self.cell is not None:
            self.parts.append(data)

    def close_cell(self, end, malformed=False):
        if self.cell is not None:
            if malformed:
                self.flag('malformed_structure')
            self.cell['char_end'] = end
            self.cell['text'] = _visible(self.parts)
            self.cell = None
            self.parts = []

    def close_row(self, end, malformed=False):
        self.close_cell(end, malformed=True)
        if self.row is not None and malformed:
            self.flag('malformed_structure')
        self.row = None

    def ensure_grid(self, rows, width):
        """Reserve rectangular grid growth before allocating any slots."""
        if self.grid_blocked:
            return False
        grid = self.result['grid']
        rows = max(rows, len(grid))
        width = max(width, self.grid_width)
        if rows == len(grid) and width == self.grid_width:
            return True
        extra = rows * width - len(grid) * self.grid_width
        if self.budget['grid_slots'] + extra > MAX_DOCUMENT_GRID_SLOTS:
            self.flag('grid_limit')
            self.grid_blocked = True
            return False
        self.budget['grid_slots'] += extra
        if width > self.grid_width:
            for row in grid:
                row.extend([None] * (width - self.grid_width))
        while len(grid) < rows:
            grid.append([None] * width)
        self.grid_width = width
        return True

    def start_row(self, start):
        if self.row is not None:
            self.close_row(start, malformed=True)
        index = self.row_count
        self.row_count += 1
        self.column = 0
        if index >= MAX_ROWS:
            self.flag('row_limit')
            return
        if self.budget['rows'] >= MAX_DOCUMENT_ROWS:
            self.flag('document_row_limit')
            return
        self.budget['rows'] += 1
        self.row = dict(row_index=index, cells=[])
        self.result['rows'].append(self.row)
        self.ensure_grid(index + 1, self.grid_width)

    def span(self, attrs, name):
        values = [value for key, value in attrs if key == name]
        if not values:
            return 1
        if len(values) > 1:
            self.flag('ambiguous_structure')
        value = values[0]
        if value is None or not value.isascii() or not value.isdigit() or len(value) > 8:
            self.flag('invalid_span' if value is None or not str(value).isdigit() else 'span_limit')
            return MAX_SPAN if value and value.isascii() and value.isdigit() else 1
        number = int(value)
        if number < 1:
            self.flag('invalid_span')
            return 1
        if number > MAX_SPAN:
            self.flag('span_limit')
        return min(number, MAX_SPAN)

    def start_cell(self, tag, attrs, start):
        self.close_cell(start, malformed=True)
        if self.row is None:
            if self.row_count >= MAX_ROWS:
                self.flag('row_limit')
                return
            if self.budget['rows'] >= MAX_DOCUMENT_ROWS:
                self.flag('document_row_limit')
                return
            self.flag('ambiguous_structure')
            self.start_row(start)
        if self.cell_count >= MAX_CELLS:
            self.flag('cell_limit')
            return
        if self.budget['cells'] >= MAX_DOCUMENT_CELLS:
            self.flag('document_cell_limit')
            return
        self.cell_count += 1
        self.budget['cells'] += 1
        row_index = self.row['row_index']
        grid = self.result['grid']
        current = grid[row_index] if row_index < len(grid) else []
        while self.column < len(current) and current[self.column] is not None:
            self.column += 1
        rowspan = self.span(attrs, 'rowspan')
        colspan = self.span(attrs, 'colspan')
        cell_id = f"{self.result['table_id']}_cell_{self.cell_count}"
        self.cell = dict(cell_id=cell_id, text='', row_index=row_index,
                         column_index=self.column, rowspan=rowspan, colspan=colspan,
                         char_start=start, char_end=start, tag=tag)
        self.parts = []
        self.row['cells'].append(self.cell)
        last_row = min(row_index + rowspan, MAX_ROWS)
        last_column = min(self.column + colspan, MAX_COLUMNS)
        if row_index + rowspan > MAX_ROWS:
            self.flag('row_limit')
        if self.column + colspan > MAX_COLUMNS:
            self.flag('column_limit')
        if self.column < MAX_COLUMNS and self.ensure_grid(last_row, last_column):
            for index in range(row_index, last_row):
                target = grid[index]
                for column in range(self.column, last_column):
                    if target[column] is not None:
                        self.flag('span_collision')
                    else:
                        target[column] = cell_id
        self.column += colspan

    def finish(self, end, malformed=False):
        self.close_row(end, malformed)
        if self.caption is not None:
            self.flag('malformed_structure')
            self.result['caption'] = _visible(self.caption)
            self.caption = None
        if malformed:
            self.flag('malformed_structure')
        grid = self.result['grid']
        if len(grid) > len(self.result['rows']):
            self.flag('dangling_rowspan')
            del grid[len(self.result['rows']):]
        self.result['char_end'] = end


class _Parser(HTMLParser):
    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.source = source
        self.lines = [0]
        self.lines.extend(index + 1 for index, char in enumerate(source) if char == '\n')
        self.tables = []
        self.active = []
        self.skip_tables = 0
        self.suppressed = []
        self.context = ''
        self.budget = {'grid_slots': 0, 'cells': 0, 'rows': 0}

    def source_offset(self):
        line, column = self.getpos()
        return self.lines[line - 1] + column

    def handle_starttag(self, tag, attrs):
        start = self.source_offset()
        if self.suppressed:
            if tag in _SUPPRESSED:
                self.suppressed.append(tag)
            return
        if tag in _SUPPRESSED:
            self.suppressed.append(tag)
            return
        if tag == 'table':
            if self.active:
                self.active[-1].flag('nested_table')
                self.active[-1].append(' ')
            if self.skip_tables:
                self.skip_tables += 1
                return
            limit = 'table_limit' if len(self.tables) >= MAX_TABLES else 'table_depth_limit'
            if len(self.tables) >= MAX_TABLES or len(self.active) >= MAX_TABLE_DEPTH:
                if self.active:
                    self.active[-1].flag(limit)
                if self.tables:
                    self.tables[-1].flag(limit)
                self.skip_tables = 1
                return
            table = _Table(f'table_{len(self.tables) + 1}', start,
                           _visible([self.context])[-MAX_CONTEXT:], self.budget)
            if self.active:
                table.flag('nested_table')
            self.tables.append(table)
            self.active.append(table)
            return
        if self.skip_tables:
            return
        if not self.active:
            if tag in _BLOCKS:
                self.context = (self.context + ' ')[-MAX_CONTEXT:]
            return
        table = self.active[-1]
        if tag == 'tr':
            table.start_row(start)
        elif tag in {'td', 'th'}:
            table.start_cell(tag, attrs, start)
        elif tag == 'caption':
            if table.caption is not None or table.result['caption']:
                table.flag('ambiguous_structure')
            table.caption = []
        elif tag in _BLOCKS:
            table.append(' ')

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in {'br', 'hr', 'img', 'input', 'meta', 'link'}:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        start = self.source_offset()
        close = self.source.find('>', start)
        end = len(self.source) if close == -1 else close + 1
        if self.suppressed:
            if tag == self.suppressed[-1]:
                self.suppressed.pop()
            return
        if self.skip_tables:
            if tag == 'table':
                self.skip_tables -= 1
            return
        if not self.active:
            if tag in _BLOCKS:
                self.context = (self.context + ' ')[-MAX_CONTEXT:]
            return
        table = self.active[-1]
        if tag == 'table':
            table.finish(end, malformed=table.row is not None or table.cell is not None)
            self.active.pop()
        elif tag == 'tr':
            if table.row is None and self.budget['rows'] < MAX_DOCUMENT_ROWS:
                table.flag('malformed_structure')
            table.close_row(start)
        elif tag in {'td', 'th'}:
            if table.cell is None:
                if (table.cell_count < MAX_CELLS and table.row_count < MAX_ROWS
                        and self.budget['cells'] < MAX_DOCUMENT_CELLS
                        and self.budget['rows'] < MAX_DOCUMENT_ROWS):
                    table.flag('malformed_structure')
            else:
                table.close_cell(end, malformed=table.cell['tag'] != tag)
        elif tag == 'caption':
            if table.caption is None:
                table.flag('malformed_structure')
            else:
                table.result['caption'] = _visible(table.caption)
                table.caption = None
        elif tag in _BLOCKS:
            table.append(' ')

    def handle_data(self, data):
        if self.suppressed or self.skip_tables:
            return
        if self.active:
            self.active[-1].append(data)
        else:
            self.context = (self.context + data)[-MAX_CONTEXT:]

    def finish(self):
        for table in reversed(self.active):
            table.finish(len(self.source), malformed=True)
        return [table.result for table in self.tables]


def extract_html_tables(text: str) -> list[dict]:
    """Return source-backed tables with unresolved text, cells and span grids.

    Coverage limits are exposed in ``quality_flags`` on affected tables. A
    global table limit is also flagged on the last retained table. No values,
    units, dates, roles or associations are inferred from table content.
    Shared document budgets cap retained rows/cells and grid allocations
    (including row/column padding). A grid-limit table retains its cells but its grid is
    incomplete; cell-limit tables retain only the cells inside the budget.
    """
    parser = _Parser(text)
    parser.feed(text)
    parser.close()
    return parser.finish()
