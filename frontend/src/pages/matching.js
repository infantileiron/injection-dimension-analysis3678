import {feedback, field} from '../components/common/fields.js';
import {empty, metrics, panel, pill} from '../components/common/panels.js';
import {table} from '../components/common/table.js';
import {handler} from '../hooks/action.js';
import {session} from '../stores/session.js';
import {workspace} from '../stores/workspace.js';
import {button, el, link, p} from '../utils/dom.js';
import {date} from '../utils/format.js';

const WINDOW_OPTIONS = [
  [300, '五分钟（300 秒，默认）'],
  [180, '三分钟（180 秒）'],
  [600, '十分钟（600 秒）'],
];
// handler 会读写 control.disabled，表单提交用提交按钮自身，这里给一个占位控件。
const noopControl = {disabled:false};

function windowField(value = 300) {
  return el('label', {for:'window-seconds', class:'field'}, el('span', {}, '配对时间窗'),
    el('select', {id:'window-seconds', name:'window_seconds'},
      WINDOW_OPTIONS.map(([v, label]) => el('option', {value:v, selected:v === value}, label))));
}

function fileField(id, labelText, {required = true} = {}) {
  const attrs = {id, type:'file', name:id, accept:'.csv,text/csv'};
  if (required) attrs.required = true;
  return el('label', {class:'field', for:id}, el('span', {}, labelText), el('input', attrs));
}

function kindPill(kind) {
  const map = {anchored:['样件号锚定','ok'], time_window:['时间窗配对','info'],
    ambiguous:['并列歧义','warn'], anchor_over_window:['超窗锚定','warn']};
  const [text, state] = map[kind] || [kind, 'warn'];
  return pill(text, state);
}

function pairColumns() {
  return [
    {key:'sample_id', label:'入算样件号'},
    {label:'配对方式', render:row => kindPill(row.match_kind)},
    {key:'machine_serial', label:'机台流水号'}, {key:'caliper_serial', label:'卡尺流水号'},
    {key:'machine_sample_id', label:'机台账件号'}, {key:'caliper_sample_id', label:'卡尺台账件号'},
    {key:'delta_seconds', label:'时差(秒)'},
  ];
}

function previewTables(summary) {
  const confident = table(pairColumns(), summary.confident_pairs,
    {caption:'本次入算配对', empty:'没有稳定配对，请核对台账。', pageSize:8});
  const review = table([
    {key:'machine_serial', label:'机台流水号'}, {key:'caliper_serial', label:'卡尺流水号'},
    {key:'machine_sample_id', label:'机台账件号'}, {key:'caliper_sample_id', label:'卡尺台账件号'},
    {key:'delta_seconds', label:'时差(秒)'}, {key:'review_reason', label:'待核对原因'},
  ], summary.review_pairs, {caption:'待核对配对', empty:'无歧义配对。', pageSize:8});
  const pending = table([
    {label:'台账', render:row => row.side === 'machine' ? '机台日志' : '卡尺记录'},
    {key:'serial', label:'流水号'}, {key:'sample_id', label:'样件号'},
    {key:'die', label:'模具'}, {key:'machine', label:'机台'},
    {key:'ts', label:'记录时间'}, {key:'review_reason', label:'原因'},
  ], summary.pending_records, {caption:'待核对记录（未配上）', empty:'无遗留记录。', pageSize:8});
  return [confident, review, pending];
}

function summaryMetrics(summary) {
  return metrics([
    {label:'分组数（日期×模具×机台）', value:summary.group_count},
    {label:'机台日志', value:summary.machine_total},
    {label:'卡尺记录', value:summary.caliper_total},
    {label:'本次入算配对', value:summary.confident_count, detail:`时间窗 ${summary.window_seconds} 秒`},
    {label:'待核对配对', value:summary.review_pair_count},
    {label:'待核对记录', value:summary.pending_count},
  ]);
}

async function readFile(input) {
  const file = input.files?.[0];
  if (!file) throw new Error('请选择 CSV 文件');
  if (file.size > 2_000_000) throw new Error('CSV 最多 2 MB');
  return {name:file.name, text:await file.text()};
}

function uploadPanel(refresh) {
  const error = feedback();
  const previewBox = el('div', {});
  const form = el('form', {class:'fields', onSubmit:handler(noopControl, error, async event => {
    event.preventDefault();
    const data = new FormData(event.target);
    const machine = await readFile(event.target.machine_csv);
    const caliper = await readFile(event.target.caliper_csv);
    const payload = {
      name:data.get('name'), machine_filename:machine.name, caliper_filename:caliper.name,
      machine_csv:machine.text, caliper_csv:caliper.text,
      window_seconds:Number(data.get('window_seconds')),
    };
    const created = await workspace.ledgerUpload(payload);
    previewBox.replaceChildren(...previewTables(created.summary));
    await refresh();
    location.hash = `#matching/${created.id}`;
  })}, field({key:'name', label:'台账批次名称', type:'string', max_length:120}),
    windowField(), fileField('machine_csv', '机台成型日志 CSV'), fileField('caliper_csv', '卡尺量测记录 CSV'),
    button('校验配对并建批次', {type:'submit', class:'primary', 'data-testid':'ledger-upload'}), error);
  return panel('双台账配对建批',
    p('按日期 × 模具 × 机台分组，五分钟窗内一对一配对：先配足件数，再让总时差最小；并列最优时只用所有配法共有的配对算相关。', 'subtle'),
    el('div', {class:'actions'},
      link('机台日志模板', '/ledgers/template/machine', {class:'quiet',
        onClick:event => {event.preventDefault();
          workspace.download('/ledgers/template/machine', '机台成型日志-模板.csv');}}),
      link('卡尺记录模板', '/ledgers/template/caliper', {class:'quiet',
        onClick:event => {event.preventDefault();
          workspace.download('/ledgers/template/caliper', '卡尺量测记录-模板.csv');}}),
      link('下载机台演示样例', '/ledgers/sample/machine', {class:'quiet',
        onClick:event => {event.preventDefault();
          workspace.download('/ledgers/sample/machine', '机台成型日志-演示样例.csv');}}),
      link('下载卡尺演示样例', '/ledgers/sample/caliper', {class:'quiet',
        onClick:event => {event.preventDefault();
          workspace.download('/ledgers/sample/caliper', '卡尺量测记录-演示样例.csv');}})),
    session.canWrite ? form : p('只读角色可查看下方批次与历史配对。', 'empty'), previewBox);
}

function supplementPanel(batch, refresh) {
  const error = feedback();
  const result = el('div', {});
  const form = el('form', {class:'fields', onSubmit:handler(noopControl, error, async event => {
    event.preventDefault();
    const data = new FormData(event.target);
    const payload = {window_seconds:Number(data.get('window_seconds')),
      machine_filename:'', caliper_filename:''};
    if (event.target.machine_csv.files?.length) {
      const f = await readFile(event.target.machine_csv);
      payload.machine_csv = f.text; payload.machine_filename = f.name;
    }
    if (event.target.caliper_csv.files?.length) {
      const f = await readFile(event.target.caliper_csv);
      payload.caliper_csv = f.text; payload.caliper_filename = f.name;
    }
    if (!payload.machine_csv && !payload.caliper_csv) throw new Error('请至少选择一本补录 CSV');
    const updated = await workspace.ledgerSupplement(batch.id, payload);
    result.replaceChildren(p(`已生成 v${updated.version}，整组重配完成。`, 'feedback'));
    await refresh();
    location.hash = `#matching/${updated.id}`;
  })}, windowField(batch.window_seconds),
    fileField('machine_csv', '补录 · 机台日志（可选）', {required:false}),
    fileField('caliper_csv', '补录 · 卡尺记录（可选）', {required:false}),
    button('补录并整组重配', {type:'submit', class:'primary', 'data-testid':'ledger-supplement'}), error, result);
  return panel(`同批补录（当前 v${batch.version}）`,
    p('迟到记录按流水号合并后对完整台账整组重配，历史配对快照保留，可在下方回查。', 'subtle'), form);
}

function versionPanel(detail) {
  const rows = detail.versions.map(snap => ({
    version:`v${snap.version}`, confident:snap.confident_count,
    review:snap.review_pair_count, pending:snap.pending_count,
    window:snap.window_seconds, created:snap.created_at, id:snap.id,
  }));
  return panel('配对版本与回查', table([
    {key:'version', label:'版本'}, {key:'confident', label:'入算配对'},
    {key:'review', label:'待核对配对'}, {key:'pending', label:'待核对记录'},
    {key:'window', label:'时间窗(秒)'}, {label:'生成时间', render:r => date(r.created)},
    {label:'回查', render:r => link('查看当时配对', `#matching/${detail.id}?snap=${r.id}`, {class:'quiet'})},
  ], rows, {caption:'配对版本', pageSize:8}));
}

function runPanel(snapshotId, spec) {
  const error = feedback();
  const form = el('form', {class:'fields', onSubmit:handler(noopControl, error, async event => {
    event.preventDefault();
    const data = new FormData(event.target);
    const params = Object.fromEntries(spec.params.map(param => [param.key, data.get(param.key)]));
    const run = await workspace.startSnapshotRun(
      {snapshot_id:snapshotId, name:data.get('name'), params});
    location.hash = `#results/${run.id}`;
  })}, field({key:'name', label:'运行名称', type:'string', max_length:120}, `快照${snapshotId}配对复算`),
    el('div', {class:'form-grid'}, spec.params.map(param => field(param))),
    button('用此配对发起复算', {type:'submit', class:'primary', 'data-testid':'snapshot-run'}), error);
  return panel('基于该配对复算', p('只用稳定（入算）配对计算秩相关，结果页列出入算配对与待核对记录。', 'subtle'), form);
}

function batchList() {
  const {ledgerBatches} = workspace;
  return panel('台账批次', table([
    {label:'批次', render:item => link(item.name, `#matching/${item.id}`)},
    {key:'version', label:'最新版本', render:item => `v${item.version}`},
    {key:'machine_count', label:'机台'}, {key:'caliper_count', label:'卡尺'},
    {key:'confident_count', label:'入算'}, {key:'pending_count', label:'待核对'},
    {label:'时间', render:item => date(item.created_at)},
  ], ledgerBatches, {caption:'台账批次', empty:'还没有台账批次，请在左侧建批。'}));
}

export async function matching(routeInfo, refresh) {
  const {spec, ledgerBatches} = workspace;
  if (!ledgerBatches.length && !routeInfo.id) {
    return el('div', {class:'two-col'},
      el('div', {class:'wide-panel'}, uploadPanel(refresh)),
      el('aside', {class:'sidebar-panel'}, panel('配对口径', el('ul', {class:'method-list'}, [
        '按日期、模具、机台分组，组内五分钟窗一对一配对。',
        '先最大化配对件数，再最小化两侧记录总时差。',
        '并列最优时，只用每种最优配法都包含的配对计算相关。',
        '样件号一致直接锚定；超窗锚定与歧义配对转待核对。',
        '同批补录合并迟到记录后整组重配，历史快照可回查。',
      ].map(text => el('li', {}, text))))));
  }

  const selected = ledgerBatches.find(item => item.id === routeInfo.id) || ledgerBatches[0];
  if (!selected) return el('div', {}, panel('双台账配对', empty('批次不存在或已被删除。', '#matching', '返回配对')));
  const detail = await workspace.getLedgerBatch(selected.id);
  const requestedSnap = Number(new URLSearchParams(location.hash.split('?')[1] || '').get('snap')) || null;
  const snapshot = detail.versions.find(item => item.id === requestedSnap) || detail.versions.at(-1);
  const result = snapshot.result;

  const head = el('div', {}, el('div', {class:'actions'},
    pill(`v${snapshot.version}`, 'info'), p(`快照 #${snapshot.id} · ${date(snapshot.created_at)}`, 'subtle')));
  const wide = el('div', {class:'wide-panel'},
    panel(`配对结果 · ${detail.name}`, head, summaryMetrics(result), ...previewTables(result)),
    versionPanel(detail),
    session.canWrite && supplementPanel(detail, refresh),
    session.canWrite && runPanel(snapshot.id, spec));
  const side = el('aside', {class:'sidebar-panel'}, batchList(),
    panel('快照指纹', el('dl', {class:'dictionary'}, [
      ['快照编号', `#${snapshot.id}`], ['配对校验', snapshot.checksum.slice(0, 16)],
      ['时间窗', `${snapshot.window_seconds} 秒`], ['操作者', snapshot.author],
    ].map(([k, v]) => el('div', {}, el('dt', {}, k), el('dd', {}, v))))));
  return el('div', {class:'two-col'}, wide, side);
}
