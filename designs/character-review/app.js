const byId = (id) => document.getElementById(id);
const statusNames = {pending: '待核对', approved: '已确认', deferred: '待考证', excluded: '暂不收录'};
const scopeNames = {
  common: ['缺失常用字', '对照 8,105 字表，补齐日常输入的字。'],
  other: ['其他语料缺字', '来自人名、专业词与繁异体词的其他缺字。'],
  recovered: ['原版恢复', '双索引一致且笔形前缀唯一，已自动采用，无需重复确认。'],
  reading: ['已有字 · 读音差异', '字已收录，语料提供了其他读音，逐一核实后再采用。'],
  base: ['现有基础字表', '查看原有读音、数字后缀及纯笔形码。'],
  all: ['全部字符', '原有字表与本轮缺字合并查看。'],
};
const state = {items: [], scope: 'common', filtered: [], selected: null, page: 0, pageSize: 50, dirty: false, saving: false, suffixEdited: false};
let toastTimer;

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function unique(values) { return [...new Set(values)]; }
function splitValues(value) { return unique(value.trim().split(/[\s,，、;；']+/).filter(Boolean)); }
function suggestedPinyin(row) {
  if (row.current.length) return unique(row.current.map((value) => value.pinyin));
  return unique([...row.extension.map((value) => value.pinyin), ...row.corpus_pinyin]);
}
function matchesScope(row, scope) {
  if (scope === 'common') return row.missing_common;
  if (scope === 'other') return row.missing_corpus && !row.missing_common;
  if (scope === 'recovered') return row.recovery?.status === 'approved';
  if (scope === 'reading') return row.reading_gap.length > 0;
  if (scope === 'base') return row.in_base;
  return true;
}
function effectiveReview(row) { return row.review || row.recovery; }
function currentStatus(row) { return effectiveReview(row)?.status || 'pending'; }
function statusLabel(row) {
  return !row.review && row.recovery?.status === 'approved' ? '原版恢复' : statusNames[currentStatus(row)];
}

function showToast(message, error = false) {
  clearTimeout(toastTimer);
  const toast = byId('toast');
  toast.textContent = message;
  toast.classList.toggle('error', error);
  toast.hidden = false;
  toastTimer = setTimeout(() => { toast.hidden = true; }, 3500);
}

function mayLeave() {
  return !state.dirty || window.confirm('这个字的修改尚未保存。放弃修改，继续切换？');
}

function updateSummary() {
  for (const scope of Object.keys(scopeNames)) {
    byId(`count-${scope}`).textContent = state.items.filter((row) => matchesScope(row, scope)).length.toLocaleString();
  }
  const common = state.items.filter((row) => row.missing_common);
  const approved = common.filter((row) => currentStatus(row) === 'approved').length;
  const recovered = common.filter((row) => !row.review && row.recovery?.status === 'approved').length;
  const handled = common.filter((row) => ['approved', 'excluded'].includes(currentStatus(row))).length;
  byId('progress-label').textContent = `${handled} / ${common.length.toLocaleString()}`;
  byId('progress-bar').style.width = `${common.length ? handled / common.length * 100 : 0}%`;
  byId('progress-detail').textContent = `原版恢复 ${recovered} · 人工确认 ${approved - recovered} · 暂不收录 ${handled - approved}`;
}

function filterItems(resetPage = true) {
  const search = byId('search').value.trim().toLowerCase();
  const status = byId('status-filter').value;
  state.filtered = state.items.filter((row) => {
    if (!matchesScope(row, state.scope) || (status !== 'all' && currentStatus(row) !== status)) return false;
    if (byId('no-reading').checked && suggestedPinyin(row).length) return false;
    if (!search) return true;
    const terms = [row.character, row.unicode, ...row.corpus_pinyin, ...row.current_shapes,
      ...row.current.flatMap((value) => [value.pinyin, value.suffix]),
      ...row.extension.flatMap((value) => [value.pinyin, value.shape]), ...row.examples,
      ...(effectiveReview(row)?.pinyin || []), ...(effectiveReview(row)?.shapes || []),
      effectiveReview(row)?.suffix || row.suffix_suggestion || ''];
    return terms.some((term) => term.toLowerCase().includes(search));
  });
  if (resetPage) state.page = 0;
  const maximum = Math.max(0, Math.ceil(state.filtered.length / state.pageSize) - 1);
  state.page = Math.min(state.page, maximum);
  renderList();
}

function renderList() {
  const list = byId('character-list');
  list.replaceChildren();
  byId('result-count').textContent = `${state.filtered.length.toLocaleString()} 字`;
  const start = state.page * state.pageSize;
  const pageItems = state.filtered.slice(start, start + state.pageSize);
  for (const row of pageItems) {
    const status = currentStatus(row);
    const button = element('button', `character-row${row.character === state.selected?.character ? ' active' : ''}`);
    button.type = 'button';
    button.setAttribute('aria-label', `${row.character} ${statusLabel(row)}`);
    button.setAttribute('aria-pressed', String(row.character === state.selected?.character));
    button.dataset.character = row.character;
    button.append(element('span', 'row-glyph', row.character));
    const detail = element('div', 'row-detail');
    detail.append(element('div', 'row-pinyin', (effectiveReview(row)?.pinyin || suggestedPinyin(row)).join(' / ') || '读音待补'));
    detail.append(element('div', 'row-unicode', row.unicode));
    button.append(detail, element('span', `row-status ${status}`, {approved: '✓', pending: '·', deferred: '◷', excluded: '−'}[status]));
    button.addEventListener('click', () => selectCharacter(row));
    list.append(button);
  }
  if (!pageItems.length) list.append(element('div', 'list-empty', '没有匹配的字，试试其他筛选。'));
  const pages = Math.max(1, Math.ceil(state.filtered.length / state.pageSize));
  byId('page-label').textContent = `${state.page + 1} / ${pages}`;
  byId('previous-page').disabled = state.page === 0;
  byId('next-page').disabled = state.page + 1 >= pages;
}

function setDirty() {
  state.dirty = true;
  byId('save-state').textContent = '有未保存的修改';
  byId('save-state').classList.add('dirty');
  byId('form-error').hidden = true;
}

function selectCharacter(row, force = false) {
  if (state.saving || (row.character !== state.selected?.character && !force && !mayLeave())) return false;
  if (row.character === state.selected?.character && !force) return true;
  state.selected = row;
  state.dirty = false;
  state.suffixEdited = false;
  const review = effectiveReview(row);
  const suffixes = unique(row.current.map((value) => value.suffix));
  byId('empty-state').hidden = true;
  byId('editor').hidden = false;
  byId('large-character').textContent = row.character;
  byId('unicode-label').textContent = row.unicode;
  byId('review-status').textContent = statusLabel(row);
  byId('review-status').className = `badge ${currentStatus(row)}`;
  const tags = byId('character-tags');
  tags.replaceChildren();
  for (const label of [row.missing_common && '常用字缺口', row.in_base && '基础字库已收录',
    !row.in_base && !row.missing_common && '其他缺字', row.reading_gap.length && '读音待完善',
    row.recovery && '原版双索引一致'].filter(Boolean)) {
    tags.append(element('span', 'tag', label));
  }
  byId('pinyin').value = (review?.pinyin || suggestedPinyin(row)).join(' ');
  byId('suffix').value = review ? review.suffix : (row.in_base ? (suffixes.length === 1 ? suffixes[0] : '') : row.suffix_suggestion || '');
  byId('suffix').readOnly = row.in_base;
  byId('shapes').value = (review?.shapes || (row.in_base ? row.current_shapes : unique([...row.current_shapes, ...row.extension.map((value) => value.shape)]))).join(' ');
  byId('suffix-help').textContent = row.in_base ? '保留原版独立摘要，不从其他笔形码改写。'
    : row.recovery_issue || (row.suffix_suggestion ? `唯一笔形前缀 → ${row.suffix_suggestion}，已自动生成。` : '1～2 位，数字 1～8；有可靠笔形码时自动生成。');
  byId('value-heading').textContent = row.review ? '人工核对值' : row.recovery ? '原版恢复值' : '待核对值';
  byId('shape-verified').checked = review?.shape_verified || false;
  byId('notes').value = review?.notes || '';
  byId('form-error').hidden = true;
  byId('save-state').textContent = row.review ? `已保存 · 第 ${row.review.revision} 版`
    : row.recovery?.status === 'approved' ? '已自动采用 · 无需人工确认'
    : row.recovery ? '原码已恢复 · 后缀待核对' : '来源预填 · 尚未确认';
  byId('save-state').classList.remove('dirty');
  document.querySelector('.history').open = false;
  byId('history-list').textContent = '展开后读取本地记录。';
  byId('history-count').textContent = row.review ? `${row.review.revision} 次` : '';
  renderSources(row);
  renderList();
  return true;
}

function sourceBlock(title, badge) {
  const block = element('section', 'reference-block');
  const heading = element('div', 'reference-title');
  heading.append(element('h4', '', title), element('span', 'source-badge', badge));
  block.append(heading);
  return block;
}

function chips(values) {
  const container = element('div', 'source-values');
  values.forEach((value) => container.append(element('span', 'value-chip', value)));
  return container;
}

function action(label, callback) {
  const button = element('button', 'text-button', label);
  button.type = 'button';
  button.addEventListener('click', () => { if (!state.saving) { callback(); setDirty(); } });
  return button;
}

function renderSources(row) {
  const container = byId('source-content');
  container.replaceChildren();
  const corpus = sourceBlock('语料读音线索', 'lexicon');
  if (row.corpus_pinyin.length) {
    corpus.append(chips(row.corpus_pinyin));
    corpus.append(action('加入这些读音 ↙', () => {
      byId('pinyin').value = unique([...splitValues(byId('pinyin').value), ...row.corpus_pinyin]).join(' ');
    }));
  } else corpus.append(element('p', 'source-empty', '暂无词语读音线索，需要补充单字读音来源。'));
  if (row.examples.length) {
    const examples = element('div', 'examples');
    row.examples.slice(0, 8).forEach((value) => examples.append(element('span', 'example', value)));
    corpus.append(examples);
  }
  if (row.word_count) corpus.append(element('p', '', `出现在 ${row.word_count} 个不同词中，不代表真实使用频率。`));
  corpus.append(element('p', '', '从词语注音取得，可能混入误读，请人工核实。'));
  container.append(corpus);
  const extension = sourceBlock('原版扩展表', row.recovery ? '原版恢复' : 'ABC 原码');
  if (row.recovery) extension.append(element('p', '', '拼音与笔形双索引一致，原版值已采用。音形后缀按唯一前缀生成；多个前缀时保留待核对。'));
  if (row.recovery_issue) extension.append(element('p', 'recovery-warning', row.recovery_issue));
  if (row.extension.length) {
    for (const record of row.extension) {
      const item = element('div', 'reference-record');
      item.append(chips([record.pinyin, record.shape]));
      item.append(element('p', '', record.sections.length > 1 ? '拼音、笔形双索引均有记录' : `仅${record.sections[0] === 'shape' ? '笔形' : '拼音'}索引记录`));
      const actions = element('div', 'reference-actions');
      actions.append(action('加入读音', () => {
        byId('pinyin').value = unique([...splitValues(byId('pinyin').value), record.pinyin]).join(' ');
      }), action('加入笔形', () => {
        byId('shapes').value = unique([...splitValues(byId('shapes').value), record.shape]).join(' ');
        byId('shape-verified').checked = false;
      }));
      item.append(actions);
      extension.append(item);
    }
    extension.append(element('p', '', row.in_base ? '已有字保留原版音形摘要，其他笔形前缀不会覆盖它。' : '完整笔形码的前 1～2 位一致时，自动生成音形后缀。'));
  } else extension.append(element('p', 'source-empty', '原版扩展表中未找到可用记录。'));
  container.append(extension);
  if (row.in_base) {
    const base = sourceBlock('现有基础数据', '只读参考');
    for (const record of row.current) {
      base.append(chips([record.pinyin, `后缀 ${record.suffix || '无'}`]));
      base.append(element('p', '', `内部码 ${record.code} · 基础权重 ${record.weight}`));
    }
    if (row.current_shapes.length) base.append(chips(row.current_shapes));
    container.append(base);
  }
  const strokes = sourceBlock('常规笔画参考', '非 ABC 码');
  if (row.strokes.length) {
    row.strokes.slice(0, 3).forEach((code) => strokes.append(element('div', 'stroke-display', code)));
  } else strokes.append(element('p', 'source-empty', '暂无常规笔画数据。'));
  strokes.append(element('p', '', '保留来源的笔画字母表示，仅作参考，不直接转换成 ABC 数字形码。'));
  container.append(strokes);
}

async function save(status, advance = false) {
  if (!state.selected || state.saving) return;
  const row = state.selected;
  const before = [...state.filtered];
  const index = before.findIndex((value) => value.character === row.character);
  const payload = {
    status, revision: row.review?.revision || 0,
    pinyin: splitValues(byId('pinyin').value.toLowerCase().replaceAll('u:', 'v').replaceAll('ü', 'v')),
    suffix: byId('suffix').value.trim(), shapes: splitValues(byId('shapes').value),
    shape_verified: byId('shape-verified').checked, notes: byId('notes').value.trim(),
  };
  state.saving = true;
  byId('review-form').classList.add('busy');
  byId('form-error').hidden = true;
  try {
    const response = await fetch(`/api/reviews/${encodeURIComponent(row.character)}`, {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || '保存失败');
    row.review = data.review;
    state.dirty = false;
    state.saving = false;
    updateSummary();
    filterItems(false);
    selectCharacter(row, true);
    if (advance) {
      const next = before.slice(index + 1).find((value) => state.filtered.includes(value));
      if (next) {
        state.page = Math.floor(state.filtered.indexOf(next) / state.pageSize);
        selectCharacter(next, true);
        byId('character-list').querySelector('.active')?.scrollIntoView({block: 'nearest'});
      } else {
        showToast(`${row.character} 已保存 · 本轮已到队列末尾`);
        return;
      }
    }
    showToast(`${row.character} · ${statusNames[status]}，已写入 SQLite`);
  } catch (error) {
    byId('form-error').textContent = error.message;
    byId('form-error').hidden = false;
    showToast(error.message, true);
  } finally {
    state.saving = false;
    byId('review-form').classList.remove('busy');
  }
}

function navigateCharacter(direction) {
  if (!state.selected) return;
  const index = state.filtered.findIndex((row) => row.character === state.selected.character);
  const next = state.filtered[index + direction];
  if (next && selectCharacter(next)) {
    state.page = Math.floor((index + direction) / state.pageSize);
    renderList();
    byId('character-list').querySelector('.active')?.scrollIntoView({block: 'nearest'});
  }
}

for (const button of document.querySelectorAll('.scope')) {
  button.addEventListener('click', () => {
    if (state.saving || !mayLeave()) return;
    state.dirty = false;
    state.scope = button.dataset.scope;
    document.querySelectorAll('.scope').forEach((value) => value.classList.toggle('active', value === button));
    byId('status-filter').value = ['recovered', 'base', 'all'].includes(state.scope) ? 'all' : 'pending';
    byId('scope-title').textContent = scopeNames[state.scope][0];
    byId('scope-description').textContent = scopeNames[state.scope][1];
    filterItems();
    if (state.filtered.length) selectCharacter(state.filtered[0], true);
    else {
      state.selected = null;
      byId('editor').hidden = true;
      byId('empty-state').hidden = false;
      byId('empty-state').querySelector('h3').textContent = '此范围暂无字符';
      byId('empty-state').querySelector('p').textContent = '请调整筛选条件或切换其他字表。';
      byId('source-content').replaceChildren();
    }
  });
}

for (const id of ['pinyin', 'suffix', 'shapes', 'notes', 'shape-verified']) {
  byId(id).addEventListener('input', () => {
    if (id === 'suffix' || id === 'shapes') byId('shape-verified').checked = false;
    if (id === 'suffix') state.suffixEdited = true;
    if (id === 'shapes' && !state.selected?.in_base && !state.suffixEdited) {
      const shapes = splitValues(byId('shapes').value);
      const prefixes = unique(shapes.map((shape) => shape.slice(0, 2)));
      const valid = shapes.every((shape) => /^[1-8]{1,6}$/.test(shape));
      byId('suffix').value = valid && prefixes.length === 1 ? prefixes[0] : '';
      byId('suffix-help').textContent = !valid ? '请先填写有效笔形码。' : prefixes.length > 1
        ? `存在多个前缀（${prefixes.join('、')}），请人工确定后缀。`
        : prefixes.length ? `唯一笔形前缀 → ${prefixes[0]}，已自动生成。` : '暂无笔形码，后缀可暂缺。';
    }
    setDirty();
  });
}
byId('search').addEventListener('input', () => filterItems());
byId('status-filter').addEventListener('change', () => filterItems());
byId('no-reading').addEventListener('change', () => filterItems());
byId('previous-page').addEventListener('click', () => { state.page -= 1; renderList(); byId('character-list').scrollTop = 0; });
byId('next-page').addEventListener('click', () => { state.page += 1; renderList(); byId('character-list').scrollTop = 0; });
byId('previous-character').addEventListener('click', () => navigateCharacter(-1));
byId('next-character').addEventListener('click', () => navigateCharacter(1));
byId('review-form').addEventListener('submit', (event) => { event.preventDefault(); save('approved', true); });
byId('save-draft').addEventListener('click', () => save('pending'));
byId('defer-button').addEventListener('click', () => save('deferred', true));
byId('exclude-button').addEventListener('click', () => save('excluded', true));
byId('copy-character').addEventListener('click', async () => {
  if (!state.selected) return;
  try { await navigator.clipboard.writeText(state.selected.character); showToast('已复制汉字'); }
  catch { showToast('复制失败，请直接选中大字复制', true); }
});
document.querySelector('.history').addEventListener('toggle', async (event) => {
  if (!event.target.open || !state.selected) return;
  const character = state.selected.character;
  byId('history-list').textContent = '正在读取…';
  try {
    const response = await fetch(`/api/history?character=${encodeURIComponent(character)}`);
    if (!response.ok) throw new Error('读取历史失败');
    const data = await response.json();
    if (state.selected?.character !== character) return;
    byId('history-list').replaceChildren();
    if (!data.items.length) byId('history-list').textContent = '这个字还没有保存记录。';
    for (const record of data.items) {
      const item = element('div', 'history-item');
      item.append(element('div', '', `第 ${record.revision} 版 · ${statusNames[record.status]} · ${new Date(record.updated_at).toLocaleString()}`));
      item.append(element('div', '', `拼音 ${record.pinyin.join(' / ') || '—'} · 后缀 ${record.suffix || '—'} · 笔形 ${record.shapes.join(' / ') || '—'}`));
      if (record.notes) item.append(element('div', '', record.notes));
      byId('history-list').append(item);
    }
  } catch (error) { byId('history-list').textContent = error.message; }
});

function updateExportLinks() {
  const status = encodeURIComponent(byId('export-status').value);
  byId('export-tsv').href = `/api/export?format=tsv&status=${status}`;
  byId('export-json').href = `/api/export?format=json&status=${status}`;
}
byId('export-button').addEventListener('click', () => { updateExportLinks(); byId('export-dialog').showModal(); });
byId('export-status').addEventListener('change', updateExportLinks);
document.addEventListener('keydown', (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') { event.preventDefault(); save('pending'); }
  if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') { event.preventDefault(); save('approved', true); }
  if (['INPUT', 'TEXTAREA', 'SELECT'].includes(event.target.tagName) || byId('export-dialog').open) return;
  if (event.key === '/') { event.preventDefault(); byId('search').focus(); }
  if (event.key === 'j') navigateCharacter(1);
  if (event.key === 'k') navigateCharacter(-1);
});
window.addEventListener('beforeunload', (event) => {
  if (state.dirty || state.saving) { event.preventDefault(); event.returnValue = ''; }
});

async function initialize() {
  try {
    const response = await fetch('/api/catalog');
    if (!response.ok) throw new Error('无法读取本地字表');
    const data = await response.json();
    state.items = data.items;
    byId('database-label').textContent = 'review.sqlite3 · 修改单独保存';
    byId('database-label').title = data.metadata.database;
    byId('version-label').textContent = `BASE ${data.metadata.base_version}`;
    byId('connection-status').textContent = `${state.items.length.toLocaleString()} 字已载入 · 本地保存`;
    updateSummary();
    filterItems();
    if (state.filtered.length) selectCharacter(state.filtered[0]);
    else {
      byId('empty-state').querySelector('h3').textContent = data.metadata.comparison_available ? '此范围暂无字符' : '尚未载入缺字对比数据';
      byId('empty-state').querySelector('p').textContent = '可先切换现有基础字表，或启动时指定 --comparison-dir。';
    }
  } catch (error) {
    byId('connection-status').textContent = '连接失败';
    byId('empty-state').querySelector('h3').textContent = '字表载入失败';
    byId('empty-state').querySelector('p').textContent = error.message;
    showToast(error.message, true);
  }
}
initialize();
