'use strict';
const $ = id => document.getElementById(id);
const channels = {
  magnetic_uT: {name: 'Magnetic field', unit: 'µT', symbol: '⌁'},
  sound_pa: {name: 'Sound pressure', unit: 'Pa', symbol: '≋'},
  light_lux: {name: 'Light', unit: 'lux', symbol: '☼'},
  temperature_c: {name: 'Temperature', unit: '°C', symbol: '♧'},
};
const pages = {
  overview: ['Observation workspace', 'Compare paired signals. Find differences worth investigating.', 'Overview'],
  recordings: ['Recording archive', 'Your raw measurements, screening results, and provenance in one place.', 'Recordings'],
  protocol: ['Detection protocol', 'Fix the rule before you look at the trial.', 'Detection protocol'],
  trials: ['Blinded trials', 'Separate experimental conditions from the analysis.', 'Blinded trials'],
  review: ['AI research review', 'Use Ollama Cloud to suggest checks, not to decide what is real.', 'AI review'],
};
let state = {runs: [], plans: [], cloud_configured: false};
let selected = '', detail = null, channel = 'magnetic_uT', running = false, toastTimer;
let selectedPlan = '', chartRequest = 0;

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === 'class') node.className = value;
    else node.setAttribute(key, value);
  }
  for (const child of children.flat()) if (child !== null && child !== undefined) node.append(child);
  return node;
}
function fmt(value) {
  if (!Number.isFinite(value)) return '—';
  if (value === 0) return '0';
  return Math.abs(value) < .001 ? value.toExponential(2) : value.toLocaleString(undefined, {maximumSignificantDigits: 5});
}
function notify(message, error = false) {
  clearTimeout(toastTimer);
  $('toast').textContent = message;
  $('toast').classList.toggle('error', error);
  $('toast').hidden = false;
  toastTimer = setTimeout(() => { $('toast').hidden = true; }, error ? 10000 : 5000);
}
async function api(path, data) {
  const options = data === undefined ? {} : {method: 'POST', headers: {
    'Content-Type': 'application/json', 'X-Observatory-Token': state.csrf || ''}, body: JSON.stringify(data)};
  const response = await fetch(path, options);
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'Request failed');
  return result;
}
async function action(button, work, busyText = 'Working…') {
  if (running) return;
  running = true;
  const label = button.textContent;
  button.textContent = busyText;
  document.body.classList.add('busy');
  updateControls();
  try { await work(); }
  catch (error) { notify(error.message, true); }
  finally {
    running = false;
    button.textContent = label;
    document.body.classList.remove('busy');
    updateControls();
  }
}
function route() {
  let page = location.hash.slice(1) || 'overview';
  if (!pages[page]) page = 'overview';
  document.querySelectorAll('.page').forEach(n => { n.hidden = n.id !== `page-${page}`; });
  document.querySelectorAll('[data-page]').forEach(n => {
    n.classList.toggle('active', n.dataset.page === page);
    if (n.dataset.page === page) n.setAttribute('aria-current', 'page');
    else n.removeAttribute('aria-current');
  });
  const [title, subtitle, crumb] = pages[page];
  $('page-title').textContent = title;
  $('page-subtitle').textContent = subtitle;
  $('crumb').textContent = crumb;
}
function options(select, items, placeholder, preferred) {
  const previous = preferred === undefined ? select.value : preferred;
  select.replaceChildren(el('option', {value: ''}, placeholder), ...items.map(item => el('option', {value: item.id}, item.label)));
  if (items.some(item => item.id === previous)) select.value = previous;
}
async function refresh(preferred) {
  state = await api('/api/state');
  if (preferred !== undefined) selected = preferred;
  if (!state.runs.some(run => run.id === selected)) selected = state.runs[0]?.id || '';
  $('run-count').textContent = state.runs.length;
  $('recording-total').textContent = String(state.runs.length).padStart(2, '0');
  const baselines = state.runs.filter(run => run.kind === 'baseline');
  const trials = state.runs.filter(run => run.kind === 'trial');
  $('recording-caption').textContent = state.runs.length ? `${baselines.length} baselines · ${trials.length} analyzed trials` : 'Start with a quiet baseline';
  options($('selected-run'), state.runs, 'Choose a recording', selected);
  options($('protocol-baseline'), baselines, 'Choose a baseline');
  options($('trial-baseline'), baselines.filter(run => run.protocol), 'Choose a frozen protocol');
  options($('review-run'), trials, 'Choose an analyzed trial');
  if (trials.some(run => run.id === selected)) $('review-run').value = selected;
  $('cloud-status').textContent = state.cloud_configured ? 'Ollama Cloud configured' : 'Cloud not configured';
  $('ai-badge').textContent = state.cloud_configured ? 'KEY CONFIGURED' : 'NOT CONFIGURED';
  $('ai-badge').className = `badge ${state.cloud_configured ? 'simulated' : ''}`;
  $('cloud-help').textContent = state.cloud_configured
    ? 'The key is configured on the server. Refresh the current model catalog to begin.'
    : 'Set OLLAMA_API_KEY in the environment where you start the server, then restart it. The key is never entered in the browser.';
  if (!selectedPlan || !state.plans.some(plan => plan.id === selectedPlan)) selectedPlan = state.plans[0]?.id || '';
  options($('plan-select'), state.plans.map(p => ({id:p.id, label:`${new Date(p.created).toLocaleString()} · ${p.runs.length} runs`})), 'No plan generated', selectedPlan);
  renderArchive(); renderProtocol(); renderPlan();
  await selectRun(selected);
}
async function selectRun(id) {
  selected = id;
  const request = ++chartRequest;
  if (!id) { detail = null; renderSelected(); return; }
  $('chart-caption').textContent = 'Loading recording…';
  try {
    const value = await api(`/api/runs/${id}`);
    if (request !== chartRequest) return;
    detail = value;
    $('selected-run').value = id;
    renderSelected();
  } catch (error) {
    if (request !== chartRequest) return;
    detail = null; renderSelected(); notify(error.message, true);
  }
}
function downloadLink(id, type, label) {
  return el('a', {href: `/api/runs/${id}/${type}`, class: 'button small secondary', download: ''}, label);
}
function renderSelected() {
  const meta = detail?.meta;
  const report = meta?.report;
  const count = report ? Object.values(report.channels).filter(value => value.flagged).length : null;
  $('flag-total').textContent = count === null ? '—' : String(count).padStart(2, '0');
  $('flag-caption').textContent = count === null ? 'No analyzed trial selected' : `${count === 1 ? 'Channel exceeds' : 'Channels exceed'} the frozen threshold`;
  $('source-badge').textContent = meta?.source || 'NO RECORDING';
  $('source-badge').className = `badge ${meta ? (meta.source === 'SIMULATED' ? 'simulated' : 'warning') : ''}`;
  $('detail-name').textContent = meta?.label || 'No recording selected';
  const details = $('recording-details');
  details.replaceChildren();
  if (meta) {
    const rows = [['Experiment step', meta.kind === 'baseline' ? 'Baseline' : 'Trial'], ['Paired samples', meta.samples.toLocaleString()],
      ['Duration', `${fmt(meta.duration_s)} s`], ['Protocol', detail.protocol ? 'Frozen' : 'Not frozen'],
      ['Hardware calibration', 'Not verified']];
    for (const [key, value] of rows) details.append(el('div', {class:'detail-row'}, el('span',{},key),el('strong',{},value)));
    if (meta.baseline_label) details.append(el('p',{class:'muted'},`Compared against ${meta.baseline_label}`));
    details.append(el('div',{class:'detail-hash'},'RECORDING / SHA-256',el('code',{class:'hash'},meta.sha256)));
    const links = el('div',{class:'detail-actions'},downloadLink(meta.id,'csv','Raw CSV ↓'));
    if (report) links.append(downloadLink(meta.id,'report','Result JSON ↓'));
    if (detail.protocol) links.append(downloadLink(meta.id,'protocol','Protocol ↓'));
    if (meta.kind === 'baseline' && !detail.protocol) {
      const link = el('a',{href:'#protocol',class:'button small primary'},'Freeze protocol →');
      link.addEventListener('click',()=>{$('protocol-baseline').value=meta.id;renderProtocol();});
      links.append(link);
    }
    details.append(links);
  } else details.append(el('p',{class:'muted'},'Recordings, protocols, and numerical results are saved locally and remain available after a restart.'));
  $('result-state').textContent = report ? `${count} of 4 channels flagged` : meta ? 'Baseline · no trial comparison' : 'Select an analyzed trial';
  $('results-body').replaceChildren(...Object.entries(channels).map(([key, info]) => {
    const value = report?.channels[key];
    return el('tr',{},el('td',{},el('div',{class:'channel-cell'},el('span',{class:'channel-symbol','aria-hidden':'true'},info.symbol),el('div',{},info.name,el('br'),el('small',{},info.unit)))),
      el('td',{class:'mono'},value ? fmt(value.rms) : '—'),
      el('td',{class:'mono'},value ? fmt(value.threshold) : detail?.protocol ? fmt(detail.protocol.spec.thresholds[key]) : '—'),
      el('td',{class:'ratio'},value ? `${fmt(value.rms/value.threshold)}×` : '—'),
      el('td',{},el('span',{class:`result-pill ${value ? value.flagged ? 'flagged' : '' : 'pending'}`},value ? value.flagged ? '◌ Flagged' : '✓ Below threshold' : '— Awaiting trial')));
  }));
  renderChart(); updateControls();
}
function svg(tag, attrs = {}, text) {
  const node = document.createElementNS('http://www.w3.org/2000/svg',tag);
  for (const [key,value] of Object.entries(attrs)) node.setAttribute(key,value);
  if (text !== undefined) node.textContent = text;
  return node;
}
function renderChart() {
  const info = channels[channel];
  $('chart-unit').textContent = `${info.name} / ${info.unit}`;
  if (!detail) {
    $('chart-window').textContent = 'Awaiting recording';
    $('chart-caption').textContent = 'Both pods share a synthetic clock in simulation.';
    const button = el('button',{id:'load-demo',class:'button secondary'},'Load demonstration');
    button.addEventListener('click',loadDemo);
    $('chart').replaceChildren(el('div',{class:'empty-chart'},el('span',{class:'empty-icon'},'⌁'),el('h3',{},'Your next observation starts here'),el('p',{},'Create a baseline or explore a simulated experiment.'),button));
    return;
  }
  const data = detail.chart;
  const values = data.flatMap(point => [point.a[channel],point.b[channel]]);
  let min = Math.min(...values), max = Math.max(...values);
  const pad = Math.max((max-min)*.12, Math.abs(max)*.00001, .00001);
  min -= pad; max += pad;
  const start = data[0].t, end = data[data.length-1].t;
  const width = Math.max(300,$('chart').clientWidth), height = Math.max(220,$('chart').clientHeight);
  const left = 58, right = width-16, top = 15, bottom = height-29;
  const x = t => left+(t-start)/(end-start)*(right-left);
  const y = value => bottom-(value-min)/(max-min)*(bottom-top);
  const plot = svg('svg',{viewBox:`0 0 ${width} ${height}`,role:'img','aria-label':`${info.name} for pods A and B. ${detail.meta.source}. ${detail.total_samples} paired samples.`});
  plot.append(svg('title',{},`${info.name}: Pod A and Pod B`));
  for (let i=0;i<5;i++) {
    const value = min+(max-min)*i/4, yy=y(value);
    plot.append(svg('line',{x1:left,x2:right,y1:yy,y2:yy,class:'gridline'}));
    plot.append(svg('text',{x:left-9,y:yy+3,'text-anchor':'end'},fmt(value)));
    const t=start+(end-start)*i/4;
    plot.append(svg('text',{x:x(t),y:height-9,'text-anchor':'middle'},fmt(t)));
  }
  for (const pod of ['b','a']) plot.append(svg('polyline',{points:data.map(point=>`${x(point.t)},${y(point[pod][channel])}`).join(' '),class:`trace-${pod}`}));
  $('chart').replaceChildren(plot);
  $('chart-window').textContent = `${fmt(start)}–${fmt(end)} s`;
  $('chart-caption').textContent = `${detail.plotted_samples} displayed / ${detail.total_samples.toLocaleString()} pairs analyzed in full`;
}
function renderArchive() {
  const query = $('run-filter').value.trim().toLowerCase();
  const runs = state.runs.filter(run => run.label.toLowerCase().includes(query));
  $('archive-body').replaceChildren(...runs.map(run => {
    const button = el('button',{class:'button small secondary'},'Inspect →');
    button.addEventListener('click',()=>{location.hash='overview';selectRun(run.id);});
    return el('tr',{},el('td',{},el('span',{class:'archive-label'},run.label),el('code',{class:'archive-date'},run.sha256.slice(0,16)+'…')),
      el('td',{},run.kind,el('br'),el('span',{class:`badge ${run.source==='SIMULATED'?'simulated':'warning'}`},run.source)),
      el('td',{class:'mono'},run.samples.toLocaleString()),el('td',{class:'archive-date'},new Date(run.created).toLocaleString()),el('td',{},button));
  }));
  if (!runs.length) $('archive-body').append(el('tr',{},el('td',{colspan:'5',class:'table-empty'},query ? 'No recordings match this name.' : 'No recordings yet. Create a baseline to start.')));
}
function renderProtocol() {
  const baseline = state.runs.find(run=>run.id===$('protocol-baseline').value);
  const protocol = baseline?.protocol;
  $('protocol-help').textContent = protocol ? 'This protocol is frozen. Use it when creating a new trial.' : baseline ? 'The multiplier is fixed once this protocol is saved.' : 'Create a baseline recording first, then select it here.';
  const container = $('protocol-detail');
  container.replaceChildren();
  if (protocol) {
    const body = el('tbody');
    for (const [key,info] of Object.entries(channels)) body.append(el('tr',{},el('td',{},info.name),el('td',{class:'mono'},`${fmt(protocol.spec.thresholds[key])} ${info.unit}`)));
    container.append(el('span',{class:'badge simulated'},'FROZEN · PAIRED RMS DIFFERENCE'),el('p',{class:'muted'},`Threshold multiplier: ${protocol.spec.factor}× baseline paired RMS.`),el('table',{class:'protocol-table'},el('thead',{},el('tr',{},el('th',{},'Channel'),el('th',{},'Threshold'))),body),
      el('div',{},el('div',{class:'eyebrow'},'PROTOCOL SHA-256'),el('code',{class:'hash'},protocol.sha256)),downloadLink(baseline.id,'protocol','Download protocol ↓'));
  } else container.append(el('p',{class:'muted'},baseline ? 'No protocol saved for this baseline. Choose a multiplier and freeze the rule before collecting the trial.' : 'Choose a baseline to inspect its protocol.'));
  $('factor').disabled = !!protocol;
  updateControls();
}
function renderPlan() {
  const plan=state.plans.find(value=>value.id===selectedPlan);
  $('plan-key').replaceChildren();
  if (plan) $('plan-key').append('Custodian key saved in the private directory as ',el('code',{class:'hash'},plan.key_filename),'Share only the blinded schedule with analysts.');
  $('plan-body').replaceChildren(...(plan?.runs||[]).map(run=>el('tr',{},el('td',{class:'mono'},run.run),el('td',{},`Pod ${run.observation_pod}`),el('td',{},el('span',{class:'result-pill pending'},'Hidden')))));
  if (!plan) $('plan-body').append(el('tr',{},el('td',{colspan:'3',class:'table-empty'},'Generate a plan to see the coded schedule.')));
  updateControls();
}
function updateControls() {
  document.querySelectorAll('button').forEach(button=>{button.disabled=running;});
  const baseline=state.runs.find(run=>run.id===$('protocol-baseline').value);
  $('freeze-button').disabled=running||!baseline||!!baseline.protocol;
  $('factor').disabled=running||!!baseline?.protocol;
  $('refresh-models').disabled=running||!state.cloud_configured;
  $('explain-button').disabled=running||!state.cloud_configured||!$('review-run').value||!$('model-select').value;
  $('download-plan').disabled=running||!selectedPlan;
  const trial=$('record-kind').value==='trial';
  const importing=$('record-source').value==='import';
  $('trial-baseline-field').hidden=!trial;
  $('trial-baseline').required=trial;
  $('trial-baseline').disabled=!trial;
  $('simulation-fields').hidden=importing;
  $('import-fields').hidden=!importing;
  $('csv-file').required=importing;
  $('csv-file').disabled=!importing;
  $('simulation-fields').querySelectorAll('input').forEach(input=>{input.disabled=importing;});
  $('save-record').disabled=running||(trial&&!$('trial-baseline').value);
}
async function loadDemo(event) {
  await action(event.currentTarget,async()=>{
    const result=await api('/api/demo',{});
    await refresh(result.id);
    notify('Demonstration loaded: magnetic offset injected into pod A.');
  },'Generating…');
}
$('new-recording').addEventListener('click',()=>{
  $('record-error').textContent='';
  $('record-dialog').showModal();
  $('record-form').elements.label.focus();
  updateControls();
});
for (const id of ['close-dialog','cancel-record']) $(id).addEventListener('click',()=>$('record-dialog').close());
for (const id of ['record-kind','record-source','trial-baseline']) $(id).addEventListener('change',updateControls);
$('record-form').addEventListener('submit',event=>{
  event.preventDefault();
  action($('save-record'),async()=>{
    $('record-error').textContent='';
    try {
      const data=Object.fromEntries(new FormData($('record-form')));
      if(data.source==='import') {
        const file=$('csv-file').files[0];
        if(!file) throw new Error('Choose a CSV file.');
        if(file.size>7*1024*1024) throw new Error('Choose a CSV smaller than 7 MB.');
        data.csv=await file.text();
      }
      const result=await api('/api/record',data);
      $('record-dialog').close();
      await refresh(result.id);
      if(result.kind==='baseline') {
        $('protocol-baseline').value=result.id;renderProtocol();location.hash='protocol';
        notify('Baseline saved. Freeze its screening protocol before collecting a trial.');
      } else {location.hash='overview';notify('Trial saved and analyzed against the frozen protocol.');}
      $('record-form').reset();
    } catch(error) {$('record-error').textContent=error.message;throw error;}
  },'Recording…');
});
$('protocol-form').addEventListener('submit',event=>{
  event.preventDefault();
  action($('freeze-button'),async()=>{
    await api('/api/freeze',{id:$('protocol-baseline').value,factor:$('factor').value});
    await refresh();
    notify('Protocol frozen. Select it when creating a trial.');
  },'Freezing…');
});
$('plan-form').addEventListener('submit',event=>{
  event.preventDefault();
  action(event.submitter,async()=>{
    const plan=await api('/api/plan',{repeats:$('repeats').value});
    selectedPlan=plan.id;await refresh();notify('Blinded schedule saved. Operator key stored separately.');
  },'Randomizing…');
});
$('download-plan').addEventListener('click',()=>{
  const plan=state.plans.find(value=>value.id===selectedPlan);
  if(!plan)return;
  const url=URL.createObjectURL(new Blob([JSON.stringify(plan.runs,null,2)],{type:'application/json'}));
  const link=el('a',{href:url,download:`blinded-plan-${plan.id}.json`});
  document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
});
$('refresh-models').addEventListener('click',event=>{
  action(event.currentTarget,async()=>{
    const result=await api('/api/models',{});
    const models=(result.models||[]).map(model=>({id:model.name||model.model,label:model.name||model.model})).filter(model=>model.id);
    options($('model-select'),models,'Choose a current cloud model');
    if(models.length)$('model-select').value=models[0].id;
    notify(models.length?`${models.length} cloud models available.`:'No models returned by Ollama Cloud.',!models.length);
  },'Fetching…');
});
$('review-form').addEventListener('submit',event=>{
  event.preventDefault();
  action($('explain-button'),async()=>{
    const id=$('review-run').value, model=$('model-select').value;
    const name=state.runs.find(run=>run.id===id)?.label||id;
    $('ai-output').textContent=`Reviewing ${name} with ${model}…`;
    try {
      const result=await api('/api/explain',{id,model});
      $('ai-output').replaceChildren(el('div',{class:'eyebrow'},`${name} / ${model}`),el('p',{},result.text));
      notify('AI review received. Numerical results are unchanged.');
    } catch(error) {$('ai-output').textContent='Review could not be completed. Check cloud configuration and try again.';throw error;}
  },'Requesting review…');
});
$('selected-run').addEventListener('change',event=>selectRun(event.target.value));
$('run-filter').addEventListener('input',renderArchive);
$('protocol-baseline').addEventListener('change',renderProtocol);
$('plan-select').addEventListener('change',event=>{selectedPlan=event.target.value;renderPlan();});
for(const id of ['review-run','model-select']) $(id).addEventListener('change',updateControls);
document.querySelectorAll('[data-channel]').forEach(button=>button.addEventListener('click',()=>{
  channel=button.dataset.channel;
  document.querySelectorAll('[data-channel]').forEach(tab=>{tab.classList.toggle('active',tab===button);tab.setAttribute('aria-pressed',String(tab===button));});
  renderChart();
}));
window.addEventListener('hashchange',()=>{route();renderChart();});
let resizeTimer;
window.addEventListener('resize',()=>{clearTimeout(resizeTimer);resizeTimer=setTimeout(renderChart,100);});
route();
refresh().catch(error=>notify(`Could not load the workspace: ${error.message}`,true));
