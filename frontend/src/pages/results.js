import {plot} from '../components/common/chart.js';
import {feedback, field} from '../components/common/fields.js';
import {empty, metrics, panel, pill} from '../components/common/panels.js';
import {table} from '../components/common/table.js';
import {REVIEW, STATUS} from '../constants/enums.js';
import {handler, poll} from '../hooks/action.js';
import {session} from '../stores/session.js';
import {workspace} from '../stores/workspace.js';
import {button, el, h, link, p} from '../utils/dom.js';
import {date, value} from '../utils/format.js';

function reviewForm(item, spec, refresh) {
  const message = feedback();
  const submit = button(spec.action || '提交复核决定',{class:'primary',type:'submit','data-testid':'review-submit'});
  const action = field({key:'decision',label:spec.decision,type:spec.modes?.length ? 'select' : 'string',
    options:spec.modes,required:false,max_length:120});
  return el('form',{class:'fields',onSubmit:handler(submit,message,async event=>{
    const data = new FormData(event.target);
    await workspace.review(item.id,{review:data.get('review'),decision:data.get('decision'),note:data.get('note')});
    await refresh();
  })},el('label',{class:'field',for:'review-state'},el('span',{},'复核结论'),
    el('select',{name:'review',id:'review-state'},el('option',{value:'accepted'},'通过'),el('option',{value:'returned'},'退回'))),
    action,el('label',{class:'field',for:'review-note'},el('span',{},'复核说明'),el('textarea',{id:'review-note',name:'note',required:true,maxlength:500,rows:3})),submit,message);
}

export async function results(route, refresh) {
  const {spec,runs,datasets} = workspace;
  const id = route.id || runs[0]?.id;
  const deliveries = spec.scheduled ? await workspace.deliveries() : [];
  const distribution = spec.scheduled && panel('站内收件箱',table([
    {key:'recipient',label:'收件团队'}, {label:'回执',render:item=>pill(item.state==='delivered'?'已投递':'已拦截',item.state)},
    {key:'detail',label:'说明'}, {label:'时间',render:item=>date(item.created_at)},
    {label:'关联结果',render:item=>link(`运行 ${item.run_id}`,`#results/${item.run_id}`)},
  ],deliveries,{caption:'站内收件箱',empty:'计划执行后将在这里显示投递或拦截回执。'}));
  if (!id) return el('div',{},panel('分析结果',empty('还没有可查看的运行结果。','#run','前往运行')),distribution);
  const job = await workspace.getRun(id);
  const source = datasets.find(item => item.id === job.dataset_id);
  const message = feedback();
  const finished = item => item.status === 'complete' || item.status === 'failed';
  if (!finished(job)) {
    const original = location.hash;
    const status = el('p',{role:'status'},'后台正在计算，完成后会自动展示。');
    poll(()=>workspace.getRun(id),finished,()=>location.hash===original)
      .then(result=>{if (result && status.isConnected && location.hash===original) refresh();
        else if(status.isConnected) status.textContent='仍在执行，请点击刷新检查。';})
      .catch(error=>{if(status.isConnected) status.textContent=error.message;});
    return panel(job.name,pill(STATUS[job.status],job.status),status,button('刷新',{class:'quiet',onClick:refresh}));
  }
  const download = button('下载结果 CSV',{class:'quiet','data-testid':'export',onClick:event=>
    handler(download,message,()=>workspace.download(`/runs/${job.id}/export`,`${spec.short_name}-${job.id}.csv`))(event)});
  const history = el('label',{class:'field run-picker',for:'run-picker'},el('span',{},'切换运行记录'),
    el('select',{id:'run-picker',onChange:event=>{location.hash=`#results/${event.target.value}`;}},
      (runs.some(item=>item.id===job.id) ? runs : [job,...runs]).map(item=>el('option',{value:item.id,selected:item.id===job.id},item.name))));
  const result = job.result;
  const analysis = result ? el('section',{class:'analysis','data-testid':'analysis-complete'},
    el('div',{class:'result-head'},p(job.name,'eyeline'),h(2,result.headline),p(result.note,'intro-copy'),
      el('div',{class:'actions'},pill(STATUS[job.status],job.status),download,message)),
    metrics(result.metrics),
    result.charts.map(plot),
    (result.sections || []).map(item=>panel(item.title,p(item.text))),
    result.tables.map(item=>panel(item.title,table(item.columns,item.rows,{caption:item.title}))))
    : panel(job.name,pill(STATUS[job.status],job.status),p(job.error,'feedback'),link('返回调整参数',`#run/${job.dataset_id}`,{class:'quiet'}));
  const inputs = spec.params.map(param=>el('div',{},el('dt',{},param.label),el('dd',{},value(job.params[param.key]))));
  return el('div',{},el('div',{class:'two-col'},el('div',{class:'wide-panel'},analysis),
    el('aside',{class:'sidebar-panel'},panel('运行来源',history,
      source && link(source.name,`#inputs/${source.id}`),p(date(job.finished_at),'subtle'),
      el('dl',{class:'dictionary'},inputs)),
    result && panel(spec.decision,pill(REVIEW[job.review],job.review),
      job.review_note && el('div',{class:'decision'},p(job.decision),p(job.review_note)),
      job.review==='pending' && session.canReview && reviewForm(job,spec,refresh)))),distribution);
}
