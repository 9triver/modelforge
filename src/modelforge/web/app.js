const API = '/api/v1';

// ── Utilities ──

async function api(path, opts = {}) {
  const res = await fetch(API + path, opts);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || JSON.stringify(err));
  }
  if (res.status === 204) return null;
  return res.json();
}

function showToast(msg, type = 'success') {
  const el = document.getElementById('toast');
  el.className = `fixed bottom-6 right-6 z-50 px-4 py-3 rounded-lg shadow-lg text-sm text-white ${
    type === 'error' ? 'bg-red-600' : 'bg-green-600'
  }`;
  el.textContent = msg;
  el.classList.remove('hidden');
  setTimeout(() => el.classList.add('hidden'), 3000);
}

function showModal(name) { document.getElementById('modal-' + name).classList.remove('hidden'); }
function hideModal(name) { document.getElementById('modal-' + name).classList.add('hidden'); }

function formatTime(iso) {
  if (!iso) return '-';
  return new Date(iso).toLocaleString('zh-CN', { hour12: false });
}

function formatBytes(bytes) {
  if (!bytes) return '-';
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / 1048576).toFixed(1) + ' MB';
}

function fmtVer(ver) { return 'v' + String(ver).replace(/^v/, ''); }

function truncJson(obj, maxLen = 60) {
  const s = JSON.stringify(obj);
  return s.length > maxLen ? s.slice(0, maxLen) + '...' : s;
}

const statusColors = {
  draft: 'bg-gray-100 text-gray-700',
  registered: 'bg-blue-100 text-blue-700',
  shared: 'bg-green-100 text-green-700',
  archived: 'bg-yellow-100 text-yellow-700',
  pending: 'bg-gray-100 text-gray-700',
  running: 'bg-green-100 text-green-700',
  stopped: 'bg-red-100 text-red-700',
  failed: 'bg-red-100 text-red-700',
  development: 'bg-gray-100 text-gray-600',
  staging: 'bg-yellow-100 text-yellow-700',
  production: 'bg-green-100 text-green-700',
};

const statusLabels = {
  draft: '草稿', registered: '已注册', shared: '已共享', archived: '已归档',
  pending: '等待中', running: '运行中', stopped: '已停止', failed: '失败',
  development: '开发', staging: '预发布', production: '生产',
};

function badge(status) {
  return `<span class="px-2 py-0.5 text-xs font-medium rounded-full ${statusColors[status] || 'bg-gray-100'}">${statusLabels[status] || status}</span>`;
}

const taskTypeLabels = {
  load_forecast: '负荷预测', anomaly_detection: '异常检测',
  equipment_diagnosis: '设备诊断',
};

// ── Page Navigation ──

let currentPage = 'models';
let currentModelId = null;
let currentModelData = null;
let currentModelVersions = null;
let currentSubTab = 'overview';
let pendingAdaptGuide = null;  // diagnosis from trial eval, shown after fork

function switchPage(page) {
  currentPage = page;
  document.querySelectorAll('.page').forEach(p => p.classList.add('hidden'));

  if (page === 'model-detail') {
    document.getElementById('page-model-detail').classList.remove('hidden');
    return;
  }

  document.getElementById('page-' + page).classList.remove('hidden');
  if (page === 'models') loadModels();
}

// ── Health Check ──

async function checkHealth() {
  try {
    const h = await fetch('/health').then(r => r.json());
    document.getElementById('health-dot').innerHTML =
      `<span class="w-2 h-2 rounded-full bg-green-500"></span><span>${h.active_deployments} active</span>`;
  } catch {
    document.getElementById('health-dot').innerHTML =
      `<span class="w-2 h-2 rounded-full bg-red-500"></span><span>offline</span>`;
  }
}

// ── Models List ──

let debounceTimer;
function debounceLoadModels() {
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(loadModels, 300);
}

async function loadModels() {
  const q = document.getElementById('model-search').value;
  const task = document.getElementById('model-filter-task').value;
  const status = document.getElementById('model-filter-status').value;
  const params = new URLSearchParams();
  if (q) params.set('q', q);
  if (task) params.set('task_type', task);
  if (status) params.set('status', status);

  try {
    const models = await api('/models?' + params);
    const container = document.getElementById('model-list');
    if (!models.length) {
      container.innerHTML = '<div class="col-span-3 text-center py-12 text-gray-400">暂无模型</div>';
      return;
    }
    container.innerHTML = models.map(m => `
      <div class="bg-white rounded-xl border hover:shadow-md transition cursor-pointer p-5" onclick="openModelDetail('${m.id}')">
        <div class="flex items-start justify-between mb-3">
          <h3 class="font-medium text-gray-900 text-sm leading-tight">${m.name}</h3>
          ${badge(m.status)}
        </div>
        <p class="text-xs text-gray-500 mb-3 line-clamp-2">${m.description || '暂无描述'}</p>
        <div class="flex flex-wrap gap-1.5 mb-3">
          <span class="px-2 py-0.5 bg-purple-50 text-purple-700 text-xs rounded-full">${taskTypeLabels[m.task_type] || m.task_type}</span>
          <span class="px-2 py-0.5 bg-indigo-50 text-indigo-700 text-xs rounded-full">${m.algorithm_type}</span>
          <span class="px-2 py-0.5 bg-gray-100 text-gray-600 text-xs rounded-full">${m.framework}</span>
        </div>
        <div class="flex items-center justify-between text-xs text-gray-400">
          <span>${m.owner_org}</span>
          <span>${m.version_count} 个版本</span>
        </div>
      </div>
    `).join('');
  } catch (e) {
    showToast(e.message, 'error');
  }
}

async function createModel(e) {
  e.preventDefault();
  const fd = new FormData(e.target);
  const body = {
    name: fd.get('name'),
    task_type: fd.get('task_type'),
    algorithm_type: fd.get('algorithm_type'),
    framework: fd.get('framework'),
    owner_org: fd.get('owner_org'),
    description: fd.get('description') || null,
    algorithm_description: fd.get('algorithm_description') || null,
    tags: fd.get('tags') ? fd.get('tags').split(',').map(s => s.trim()).filter(Boolean) : null,
  };
  try {
    await api('/models', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    showToast('模型创建成功');
    hideModal('model-create');
    e.target.reset();
    loadModels();
  } catch (err) { showToast(err.message, 'error'); }
}

// ── Model Detail (full page) ──

async function openModelDetail(id) {
  try {
    const [model, versions] = await Promise.all([
      api('/models/' + id),
      api('/models/' + id + '/versions'),
    ]);
    currentModelId = id;
    currentModelData = model;
    currentModelVersions = versions;

    document.getElementById('detail-breadcrumb').textContent = model.name;
    renderDetailHeader(model);

    switchPage('model-detail');
    switchSubTab('overview');
  } catch (e) {
    showToast(e.message, 'error');
  }
}

function renderDetailHeader(model) {
  document.getElementById('detail-header').innerHTML = `
    <div class="flex items-start justify-between">
      <div>
        <h1 class="text-xl font-semibold text-gray-900">${model.name}</h1>
        <div class="flex items-center gap-3 mt-2">
          ${badge(model.status)}
          <span class="px-2 py-0.5 bg-purple-50 text-purple-700 text-xs rounded-full">${taskTypeLabels[model.task_type] || model.task_type}</span>
          <span class="px-2 py-0.5 bg-indigo-50 text-indigo-700 text-xs rounded-full">${model.algorithm_type}</span>
          <span class="px-2 py-0.5 bg-gray-100 text-gray-600 text-xs rounded-full">${model.framework}</span>
          <span class="text-xs text-gray-400">${model.owner_org}</span>
        </div>
      </div>
      <div class="flex gap-2">
        ${model.status === 'draft' ? `<button onclick="transitionStatus('registered')" class="px-3 py-1.5 bg-blue-600 text-white text-xs rounded-lg hover:bg-blue-700">注册</button>` : ''}
        ${model.status === 'registered' ? `<button onclick="transitionStatus('shared')" class="px-3 py-1.5 bg-green-600 text-white text-xs rounded-lg hover:bg-green-700">共享发布</button>` : ''}
        ${['registered', 'shared'].includes(model.status) ? `<button onclick="transitionStatus('archived')" class="px-3 py-1.5 bg-yellow-600 text-white text-xs rounded-lg hover:bg-yellow-700">归档</button>` : ''}
      </div>
    </div>
  `;
}

async function transitionStatus(target) {
  try {
    await api('/models/' + currentModelId + '/status', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ target_status: target }),
    });
    showToast('状态已更新');
    openModelDetail(currentModelId);
  } catch (e) { showToast(e.message, 'error'); }
}

// ── Sub-tab Navigation ──

function switchSubTab(tab) {
  currentSubTab = tab;
  document.querySelectorAll('.subtab-btn').forEach(b => {
    b.classList.remove('border-brand-600', 'text-brand-700');
    b.classList.add('border-transparent', 'text-gray-500', 'hover:text-gray-700');
  });
  const active = document.getElementById('subtab-' + tab);
  active.classList.add('border-brand-600', 'text-brand-700');
  active.classList.remove('border-transparent', 'text-gray-500', 'hover:text-gray-700');

  const renderers = {
    overview: renderOverviewTab,
    versions: renderVersionsTab,
    pipeline: renderPipelineTab,
    deploy: renderDeployTab,
    monitor: renderMonitorTab,
  };
  renderers[tab]();
}

// ── Sub-tab: Overview ──

function renderOverviewTab() {
  const m = currentModelData;
  const el = document.getElementById('subtab-content');
  el.innerHTML = `
    <div class="space-y-6">
      ${m.description ? `
        <div class="bg-white rounded-xl border p-5">
          <h3 class="text-sm font-medium text-gray-700 mb-2">模型描述</h3>
          <p class="text-sm text-gray-600">${m.description}</p>
        </div>
      ` : ''}

      ${m.algorithm_description ? `
        <div class="bg-white rounded-xl border p-5">
          <h3 class="text-sm font-medium text-gray-700 mb-2">算法说明</h3>
          <p class="text-sm text-gray-600 whitespace-pre-line">${m.algorithm_description}</p>
        </div>
      ` : ''}

      <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div class="bg-white rounded-xl border p-4">
          <div class="text-xs text-gray-500 mb-1">任务类型</div>
          <div class="text-sm font-medium">${taskTypeLabels[m.task_type] || m.task_type}</div>
        </div>
        <div class="bg-white rounded-xl border p-4">
          <div class="text-xs text-gray-500 mb-1">算法</div>
          <div class="text-sm font-medium">${m.algorithm_type}</div>
        </div>
        <div class="bg-white rounded-xl border p-4">
          <div class="text-xs text-gray-500 mb-1">框架</div>
          <div class="text-sm font-medium">${m.framework}</div>
        </div>
        <div class="bg-white rounded-xl border p-4">
          <div class="text-xs text-gray-500 mb-1">所属单位</div>
          <div class="text-sm font-medium">${m.owner_org}</div>
        </div>
      </div>

      ${m.applicable_scenarios ? `
        <div class="bg-white rounded-xl border p-5">
          <h3 class="text-sm font-medium text-gray-700 mb-2">适用场景</h3>
          <pre class="text-xs bg-gray-50 p-3 rounded-lg overflow-x-auto">${JSON.stringify(m.applicable_scenarios, null, 2)}</pre>
        </div>
      ` : ''}

      ${m.input_schema ? `
        <div class="bg-white rounded-xl border p-5">
          <h3 class="text-sm font-medium text-gray-700 mb-2">输入 Schema</h3>
          <pre class="text-xs bg-gray-50 p-3 rounded-lg overflow-x-auto">${JSON.stringify(m.input_schema, null, 2)}</pre>
        </div>
      ` : ''}

      ${m.output_schema ? `
        <div class="bg-white rounded-xl border p-5">
          <h3 class="text-sm font-medium text-gray-700 mb-2">输出 Schema</h3>
          <pre class="text-xs bg-gray-50 p-3 rounded-lg overflow-x-auto">${JSON.stringify(m.output_schema, null, 2)}</pre>
        </div>
      ` : ''}

      ${m.tags && m.tags.length ? `
        <div class="bg-white rounded-xl border p-5">
          <h3 class="text-sm font-medium text-gray-700 mb-2">标签</h3>
          <div class="flex flex-wrap gap-2">
            ${m.tags.map(t => `<span class="px-2 py-1 bg-gray-100 text-gray-700 text-xs rounded-full">${t}</span>`).join('')}
          </div>
        </div>
      ` : ''}

      <div class="bg-white rounded-xl border p-5">
        <h3 class="text-sm font-medium text-gray-700 mb-2">时间信息</h3>
        <div class="grid grid-cols-2 gap-4 text-sm text-gray-600">
          <div>创建时间: ${formatTime(m.created_at)}</div>
          <div>更新时间: ${formatTime(m.updated_at)}</div>
        </div>
      </div>

      ${currentModelVersions.length ? `
      <div class="bg-white rounded-xl border p-5">
        <h3 class="text-sm font-medium text-gray-700 mb-3">模型复用</h3>
        <p class="text-xs text-gray-500 mb-3">将此模型的某个版本 Fork 到新的组织/模型中，用于本地化调优</p>
        <button onclick="showForkDialog()"
          class="px-4 py-2 text-sm rounded-lg border border-indigo-300 text-indigo-700 bg-indigo-50 hover:bg-indigo-100">
          \u2442 Fork 到新模型
        </button>
      </div>
      ` : ''}
    </div>
  `;
}

// ── Lineage helpers ──

function findParentVersionStr(parentId) {
  const pv = (currentModelVersions || []).find(v => v.id === parentId);
  return pv ? fmtVer(pv.version) : '外部版本';
}

// ── Sub-tab: Versions ──

let expandedVersionId = null;
let activePipelineStage = 'data_prep';
let artifactTabCache = {};

const pipelineStages = [
  { key: 'data_prep', label: '数据准备', step: '①',
    categories: ['datasets', 'features'],
    categoryLabels: { datasets: '📊 数据集', features: '📋 特征定义' } },
  { key: 'training', label: '训练配置', step: '②',
    categories: ['code', 'params'],
    categoryLabels: { code: '💻 训练代码', params: '⚙ 超参数' } },
  { key: 'output', label: '模型产出', step: '③',
    categories: [],
    categoryLabels: {} },
];

function renderVersionsTab() {
  const versions = currentModelVersions;
  const el = document.getElementById('subtab-content');

  // Default expand the first version
  if (expandedVersionId === null && versions.length) {
    expandedVersionId = versions[0].id;
  }

  el.innerHTML = `
    <div class="flex items-center justify-between mb-4">
      <h3 class="text-sm font-medium text-gray-700">模型版本 (${versions.length})</h3>
      <div class="flex gap-2">
        <button onclick="showCreateDraftDialog()" class="px-3 py-1.5 bg-amber-500 text-white text-xs rounded-lg hover:bg-amber-600">+ 准备新版本</button>
        <button onclick="document.getElementById('upload-asset-id').value='${currentModelId}';showModal('upload-version')" class="px-3 py-1.5 bg-brand-600 text-white text-xs rounded-lg hover:bg-brand-700">+ 上传版本</button>
      </div>
    </div>
    ${versions.length ? `<div class="space-y-3">${versions.map(v => {
      const isExpanded = expandedVersionId === v.id;
      return `
      <div class="bg-white rounded-xl border overflow-hidden">
        <div class="p-5 cursor-pointer hover:bg-gray-50/50 transition" onclick="toggleArtifacts('${v.id}')">
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-3">
              <svg class="w-4 h-4 text-gray-400 transition-transform ${isExpanded ? 'rotate-90' : ''}" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"/>
              </svg>
              <span class="font-mono text-sm font-semibold">${fmtVer(v.version)}</span>
              ${badge(v.stage)}
              ${v.parent_version_id ? `<span class="text-xs text-purple-600 bg-purple-50 px-1.5 py-0.5 rounded">\u2190 ${findParentVersionStr(v.parent_version_id)}</span>` : ''}
              ${v.source_model_id ? '<span class="text-xs text-indigo-600 bg-indigo-50 px-1.5 py-0.5 rounded">\u2442 Fork</span>' : ''}
              <span class="text-xs text-gray-400">${v.stage === 'draft' ? '待训练' : formatBytes(v.file_size_bytes)}</span>
              <span class="text-xs text-gray-400">${v.stage === 'draft' ? '' : v.file_format}</span>
            </div>
            <span class="text-xs text-gray-400">${formatTime(v.created_at)}</span>
          </div>
          ${v.description ? `<p class="text-sm text-gray-500 mt-2 ml-7">${v.description}</p>` : ''}
          ${v.metrics ? `
            <div class="flex flex-wrap gap-4 mt-2 ml-7">
              ${Object.entries(v.metrics).map(([k, val]) =>
                `<div class="text-sm"><span class="text-gray-500">${k}:</span> <span class="font-medium">${typeof val === 'number' ? val.toFixed(2) : val}</span></div>`
              ).join('')}
            </div>
          ` : ''}
        </div>
        <div id="artifacts-panel-${v.id}" class="${isExpanded ? '' : 'hidden'}">
          <div class="border-t">
            <div class="flex items-stretch gap-0 p-4 bg-gray-50/50">
              ${pipelineStages.map((s, i) => `
                ${i > 0 ? '<div class="flex items-center px-2 text-gray-300 text-lg flex-shrink-0">→</div>' : ''}
                <button onclick="event.stopPropagation();switchPipelineStage('${v.id}','${s.key}')"
                  id="stage-${s.key}-${v.id}"
                  class="flex-1 p-3 rounded-lg border-2 text-left cursor-pointer transition
                    ${activePipelineStage === s.key && isExpanded
                      ? 'border-brand-500 bg-white shadow-sm'
                      : 'border-transparent bg-white/60 hover:bg-white hover:border-gray-200'}">
                  <div class="text-xs font-semibold ${activePipelineStage === s.key && isExpanded ? 'text-brand-700' : 'text-gray-700'}">${s.step} ${s.label}</div>
                  <div class="text-[10px] mt-1 ${activePipelineStage === s.key && isExpanded ? 'text-brand-500' : 'text-gray-400'}">
                    ${s.categories.length ? Object.values(s.categoryLabels).join(' · ') : '📦 权重文件 · 指标'}
                  </div>
                </button>
              `).join('')}
            </div>
            <div id="stage-content-${v.id}" class="p-4 min-h-[200px]"></div>
          </div>
        </div>
      </div>`;
    }).join('')}</div>` : '<div class="text-sm text-gray-400 py-12 text-center">暂无版本</div>'}
  `;

  // Load the active stage for the expanded version
  if (expandedVersionId) loadPipelineStage(expandedVersionId, activePipelineStage);
}

function toggleArtifacts(versionId) {
  if (expandedVersionId === versionId) {
    expandedVersionId = null;
  } else {
    expandedVersionId = versionId;
    activePipelineStage = 'data_prep';
    artifactTabCache = {};
  }
  renderVersionsTab();
}

function switchPipelineStage(versionId, stageKey) {
  activePipelineStage = stageKey;
  pipelineStages.forEach(s => {
    const btn = document.getElementById('stage-' + s.key + '-' + versionId);
    if (!btn) return;
    const title = btn.querySelector('div:first-child');
    const sub = btn.querySelector('div:last-child');
    if (s.key === stageKey) {
      btn.classList.remove('border-transparent', 'bg-white/60', 'hover:bg-white', 'hover:border-gray-200');
      btn.classList.add('border-brand-500', 'bg-white', 'shadow-sm');
      title.classList.replace('text-gray-700', 'text-brand-700');
      sub.classList.replace('text-gray-400', 'text-brand-500');
    } else {
      btn.classList.add('border-transparent', 'bg-white/60', 'hover:bg-white', 'hover:border-gray-200');
      btn.classList.remove('border-brand-500', 'bg-white', 'shadow-sm');
      title.classList.replace('text-brand-700', 'text-gray-700');
      sub.classList.replace('text-brand-500', 'text-gray-400');
    }
  });
  loadPipelineStage(versionId, stageKey);
}

async function loadPipelineStage(versionId, stageKey) {
  const container = document.getElementById('stage-content-' + versionId);
  if (!container) return;

  const cacheKey = versionId + ':' + stageKey;

  if (artifactTabCache[cacheKey]) {
    renderStageContent(container, stageKey, artifactTabCache[cacheKey], versionId);
    return;
  }

  const stage = pipelineStages.find(s => s.key === stageKey);

  // Output stage: render from version object, no API call
  if (stageKey === 'output') {
    const version = currentModelVersions.find(v => v.id === versionId);
    const data = { version };
    artifactTabCache[cacheKey] = data;
    renderStageContent(container, stageKey, data, versionId);
    return;
  }

  container.innerHTML = '<div class="text-xs text-gray-400 py-8 text-center">加载中...</div>';

  try {
    const base = `/models/${currentModelId}/versions/${versionId}`;
    const results = await Promise.all(
      stage.categories.map(cat => api(base + '/artifacts/' + cat).catch(() => []))
    );
    const filesMap = {};
    stage.categories.forEach((cat, i) => { filesMap[cat] = results[i]; });
    artifactTabCache[cacheKey] = filesMap;
    renderStageContent(container, stageKey, filesMap, versionId);
  } catch (e) {
    container.innerHTML = `<div class="text-xs text-red-500 py-8 text-center">${e.message}</div>`;
  }
}

function renderStageContent(container, stageKey, data, versionId) {
  // Output stage: show model weights + metrics
  if (stageKey === 'output') {
    const v = data.version;

    // Draft version: show training prompt instead of weights
    if (v.stage === 'draft') {
      container.innerHTML = `
        <div class="text-center py-8">
          <div class="text-amber-400 text-4xl mb-3">&#9881;</div>
          <h4 class="text-sm font-medium text-gray-700 mb-2">草稿版本 — 尚未训练</h4>
          <p class="text-xs text-gray-500 mb-4">请在前两个阶段准备好数据和训练配置，然后点击下方按钮开始训练</p>
          <button onclick="startDraftTraining('${v.version}')"
            class="px-6 py-2.5 bg-green-600 text-white text-sm rounded-lg hover:bg-green-700 font-medium">
            开始训练
          </button>
          <button onclick="archiveDraft('${v.id}')"
            class="ml-3 px-4 py-2 text-sm text-red-600 hover:bg-red-50 rounded-lg border border-red-200">
            废弃草稿
          </button>
        </div>`;
      return;
    }

    // Build adaptation guidance banner if pending
    let guideBannerHtml = '';
    if (pendingAdaptGuide && pendingAdaptGuide.diagnosis && v.source_model_id) {
      const diag = pendingAdaptGuide.diagnosis;
      const recs = diag.recommendations || [];
      const drifted = (diag.drift_report || []).filter(f => f.psi_severity !== 'none');

      let recListHtml = recs.map(function(r) {
        var icons = { critical: '&#10007;', warning: '&#9888;', info: '&#8505;' };
        var colors = {
          critical: 'text-red-700',
          warning: 'text-yellow-700',
          info: 'text-blue-700',
        };
        var c = colors[r.severity] || colors.info;
        return '<li class="flex gap-1.5 ' + c + '">' +
          '<span class="flex-shrink-0">' + (icons[r.severity] || '') + '</span>' +
          '<span>' + r.message + '</span></li>';
      }).join('');

      let driftHtml = '';
      if (drifted.length) {
        var driftItems = drifted.slice(0, 5).map(function(f) {
          return '<span class="px-2 py-0.5 bg-amber-100 text-amber-800 text-[10px] rounded-full">' +
            f.name + ' (PSI=' + f.psi.toFixed(2) + ')</span>';
        }).join(' ');
        driftHtml = '<div class="mt-2"><span class="text-xs text-gray-500">漂移特征: </span>' + driftItems + '</div>';
      }

      let stepsHtml =
        '<div class="mt-3 flex flex-wrap gap-2">' +
          '<span class="px-2.5 py-1 bg-white border rounded-lg text-xs text-gray-700 font-medium">① 上传本地数据</span>' +
          '<span class="text-gray-300 flex items-center">→</span>' +
          '<span class="px-2.5 py-1 bg-white border rounded-lg text-xs text-gray-700 font-medium">② 调整特征定义</span>' +
          '<span class="text-gray-300 flex items-center">→</span>' +
          '<span class="px-2.5 py-1 bg-white border rounded-lg text-xs text-gray-700 font-medium">③ 重新训练</span>' +
        '</div>';

      guideBannerHtml =
        '<div class="bg-indigo-50 border border-indigo-200 rounded-lg p-4 relative">' +
          '<button onclick="dismissAdaptGuide()" class="absolute top-2 right-2 text-indigo-300 hover:text-indigo-500 text-sm" title="关闭">&#10005;</button>' +
          '<h4 class="text-sm font-semibold text-indigo-800 mb-2">适配指南 — 试评估诊断结果</h4>' +
          '<ul class="space-y-1 text-xs leading-relaxed">' + recListHtml + '</ul>' +
          driftHtml +
          stepsHtml +
        '</div>';
    }

    container.innerHTML = `
      <div class="space-y-4">
        ${guideBannerHtml}
        <div class="bg-gray-50 rounded-lg p-4">
          <h4 class="text-xs font-semibold text-gray-700 mb-3">📦 模型权重</h4>
          <div class="flex flex-wrap gap-4 text-sm">
            <div><span class="text-gray-500">格式:</span> <span class="font-medium">${v.file_format}</span></div>
            <div><span class="text-gray-500">大小:</span> <span class="font-medium">${formatBytes(v.file_size_bytes)}</span></div>
            ${v.file_path ? `<div><span class="text-gray-500">路径:</span> <span class="font-mono text-xs">${v.file_path}</span></div>` : ''}
          </div>
        </div>
        ${v.metrics && Object.keys(v.metrics).length ? `
          <div class="bg-gray-50 rounded-lg p-4">
            <h4 class="text-xs font-semibold text-gray-700 mb-3">📊 评估指标</h4>
            <div class="grid grid-cols-2 sm:grid-cols-3 gap-3">
              ${Object.entries(v.metrics).map(([k, val]) => `
                <div class="bg-white rounded-lg p-3 border">
                  <div class="text-xs text-gray-500">${k}</div>
                  <div class="text-lg font-semibold text-gray-900 mt-1">${typeof val === 'number' ? val.toFixed(4) : val}</div>
                </div>
              `).join('')}
            </div>
          </div>
        ` : '<div class="text-xs text-gray-400 py-8 text-center">暂无评估指标</div>'}
        <div class="flex justify-end gap-2 pt-2">
          <button onclick="showRetrain('${versionId}')"
            class="px-4 py-2 text-sm text-green-600 hover:bg-green-50 rounded-lg border border-green-200 font-medium">
            重新训练
          </button>
          <button onclick="showTrialEvaluate('${versionId}')"
            class="px-4 py-2 text-sm text-brand-600 hover:bg-brand-50 rounded-lg border border-brand-200 font-medium">
            试评估
          </button>
        </div>
      </div>
    `;
    return;
  }

  // Data prep / Training stages: show grouped files
  const stage = pipelineStages.find(s => s.key === stageKey);
  const allEmpty = stage.categories.every(cat => !data[cat] || !data[cat].length);

  if (allEmpty) {
    container.innerHTML = `
      <div class="space-y-3">
        ${stage.categories.map(cat => `
          <div class="flex items-center justify-between py-2">
            <span class="text-xs text-gray-500">${stage.categoryLabels[cat]}</span>
            <button onclick="showUploadArtifact('${versionId}','${cat}')"
              class="px-2 py-1 text-xs text-brand-600 hover:bg-brand-50 rounded border border-brand-200">+ 上传文件</button>
          </div>
        `).join('')}
      </div>`;
    return;
  }

  const isTextFile = name => /\.(py|yaml|yml|txt|json|md|cfg|ini|toml)$/.test(name);

  container.innerHTML = `
    <div class="space-y-4">
      ${stage.categories.map(cat => {
        const files = data[cat] || [];
        const csvFiles = files.filter(f => f.name.endsWith('.csv'));
        return `
          <div>
            <div class="flex items-center justify-between mb-2">
              <h4 class="text-xs font-semibold text-gray-600">${stage.categoryLabels[cat]} <span class="text-gray-400 font-normal">(${files.length})</span></h4>
              <button onclick="showUploadArtifact('${versionId}','${cat}')"
                class="px-2 py-1 text-xs text-brand-600 hover:bg-brand-50 rounded border border-brand-200">+ 上传文件</button>
            </div>
            ${files.length ? `<div class="flex flex-wrap gap-2">
              ${files.map(f => `
                <div class="flex items-center gap-0.5">
                  <button onclick="viewArtifact('${versionId}','${cat}','${f.name}')"
                    class="artifact-btn px-3 py-1.5 text-xs rounded-lg border hover:bg-gray-50 flex items-center gap-1.5">
                    <span class="${fileIcon(f.name)}">${fileIconChar(f.name)}</span>
                    <span>${f.name}</span>
                    <span class="text-gray-400">${formatBytes(f.size)}</span>
                  </button>
                  ${isTextFile(f.name) ? `<button onclick="editArtifact('${versionId}','${cat}','${f.name}')"
                    class="p-1 text-gray-400 hover:text-blue-600" title="编辑">
                    <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                        d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"/>
                    </svg>
                  </button>` : ''}
                  <button onclick="deleteArtifact('${versionId}','${cat}','${f.name}')"
                    class="p-1 text-gray-400 hover:text-red-600" title="删除">
                    <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                        d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/>
                    </svg>
                  </button>
                </div>
              `).join('')}
            </div>` : '<div class="text-xs text-gray-400 py-2">暂无文件</div>'}
            ${csvFiles.length ? `<div class="flex flex-wrap gap-2 mt-2">${csvFiles.map(f =>
              `<button onclick="previewDataset('${versionId}','${f.name}')"
                class="px-3 py-1 text-xs bg-green-50 text-green-700 rounded-lg border border-green-200 hover:bg-green-100">
                预览 ${f.name}
              </button>`
            ).join('')}</div>` : ''}
            <div id="artifact-view-${cat}-${versionId}"></div>
          </div>
        `;
      }).join('')}
    </div>
  `;
}

function fileIcon(name) {
  if (name.endsWith('.py')) return 'text-blue-500';
  if (name.endsWith('.csv')) return 'text-green-500';
  if (name.endsWith('.yaml') || name.endsWith('.yml')) return 'text-yellow-600';
  if (name.endsWith('.txt')) return 'text-gray-500';
  return 'text-gray-400';
}

function fileIconChar(name) {
  if (name.endsWith('.py')) return 'PY';
  if (name.endsWith('.csv')) return 'CSV';
  if (name.endsWith('.yaml') || name.endsWith('.yml')) return 'YML';
  if (name.endsWith('.txt')) return 'TXT';
  return '...';
}

function langForFile(name) {
  if (name.endsWith('.py')) return 'python';
  if (name.endsWith('.yaml') || name.endsWith('.yml')) return 'yaml';
  return 'plaintext';
}

async function viewArtifact(versionId, category, filename) {
  const viewId = `artifact-view-${category}-${versionId}`;
  const container = document.getElementById(viewId);
  if (!container) return;

  // Toggle: if already showing this file, hide it
  if (container.dataset.currentFile === filename) {
    container.innerHTML = '';
    container.dataset.currentFile = '';
    return;
  }

  container.innerHTML = '<div class="text-xs text-gray-400 py-2">加载中...</div>';
  try {
    const res = await fetch(API + `/models/${currentModelId}/versions/${versionId}/artifacts/${category}/${filename}`);
    if (!res.ok) throw new Error('Failed to load file');
    const text = await res.text();
    const lang = langForFile(filename);

    container.innerHTML = `
      <div class="mt-2 rounded-lg overflow-hidden border">
        <div class="bg-gray-100 px-3 py-1.5 text-xs text-gray-500 flex items-center justify-between border-b">
          <span>${filename}</span>
          <span>${lang}</span>
        </div>
        <pre class="!m-0 !rounded-none"><code class="language-${lang}">${escapeHtml(text)}</code></pre>
      </div>
    `;
    container.dataset.currentFile = filename;
    container.querySelectorAll('pre code').forEach(block => hljs.highlightElement(block));
  } catch (e) {
    container.innerHTML = `<div class="text-xs text-red-500 py-2">${e.message}</div>`;
  }
}

function escapeHtml(text) {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

let activeTabulator = null;

async function previewDataset(versionId, filename) {
  const viewId = `artifact-view-datasets-${versionId}`;
  const container = document.getElementById(viewId);
  if (!container) return;

  // Toggle
  if (container.dataset.currentFile === filename && container.innerHTML) {
    container.innerHTML = '';
    container.dataset.currentFile = '';
    if (activeTabulator) { activeTabulator.destroy(); activeTabulator = null; }
    return;
  }

  container.innerHTML = '<div class="text-xs text-gray-400 py-2">加载数据预览...</div>';
  try {
    // Load metadata if available
    let metaHtml = '';
    try {
      const metaRes = await fetch(API + `/models/${currentModelId}/versions/${versionId}/artifacts/datasets/data.yaml`);
      if (metaRes.ok) {
        const metaText = await metaRes.text();
        // Parse simple YAML fields for display
        const lines = metaText.split('\n');
        const meta = {};
        for (const line of lines) {
          const m = line.match(/^(\w+):\s*(.+)/);
          if (m) meta[m[1]] = m[2].replace(/^['"]|['"]$/g, '');
        }
        if (meta.name || meta.records) {
          metaHtml = `
            <div class="bg-blue-50 rounded-lg p-3 mb-3 text-xs text-blue-800">
              ${meta.name ? `<span class="font-medium">${meta.name}</span>` : ''}
              ${meta.records ? ` &mdash; ${meta.records} 条记录` : ''}
              ${meta.frequency ? ` &mdash; ${meta.frequency}` : ''}
              ${meta.source ? ` &mdash; 来源: ${meta.source}` : ''}
            </div>
          `;
        }
      }
    } catch {}

    const data = await api(`/models/${currentModelId}/versions/${versionId}/datasets/${filename}/preview?limit=100`);

    container.innerHTML = `
      ${metaHtml}
      <div class="mt-2 rounded-lg overflow-hidden border">
        <div class="bg-gray-100 px-3 py-1.5 text-xs text-gray-500 flex items-center justify-between border-b">
          <span>${filename} &mdash; 显示前 ${Math.min(data.limit, data.total_rows)} / ${data.total_rows} 行</span>
          <span>${data.columns.length} 列</span>
        </div>
        <div id="dataset-table-${versionId}" style="max-height: 400px;"></div>
      </div>
    `;
    container.dataset.currentFile = filename;

    // Build Tabulator
    if (activeTabulator) { activeTabulator.destroy(); activeTabulator = null; }
    const columns = data.columns.map((col, i) => ({
      title: `<span>${col}</span><br><span style="font-weight:normal;color:#9ca3af;font-size:10px">${data.dtypes[col]}</span>`,
      field: col,
      headerSort: true,
      width: 130,
    }));
    const rows = data.rows.map(row => {
      const obj = {};
      data.columns.forEach((col, i) => { obj[col] = row[i]; });
      return obj;
    });

    activeTabulator = new Tabulator('#dataset-table-' + versionId, {
      data: rows,
      columns: columns,
      layout: 'fitDataFill',
      height: '380px',
      headerSortTristate: true,
    });
  } catch (e) {
    container.innerHTML = `<div class="text-xs text-red-500 py-2">${e.message}</div>`;
  }
}

async function uploadVersion(e) {
  e.preventDefault();
  const fd = new FormData(e.target);
  const assetId = fd.get('asset_id');
  fd.delete('asset_id');
  try {
    await fetch(API + '/models/' + assetId + '/versions', { method: 'POST', body: fd })
      .then(r => { if (!r.ok) return r.json().then(j => { throw new Error(j.detail); }); return r.json(); });
    showToast('版本上传成功');
    hideModal('upload-version');
    e.target.reset();
    if (currentModelId === assetId) {
      openModelDetail(assetId);
    }
  } catch (err) { showToast(err.message, 'error'); }
}

// ── Sub-tab: Pipeline Definition ──

let pipelineEditMode = false;

const PIPELINE_TEMPLATE = `data_prep:
  dataset: data.csv
  feature_config: features.yaml

training:
  script: train.py
  params: hyperparams.yaml
  requirements: requirements.txt

output:
  format: joblib
  metrics: [rmse, mae, mape]
`;

const pipelineStagesMeta = [
  { key: 'data_prep', label: '数据准备', step: '①' },
  { key: 'training', label: '训练配置', step: '②' },
  { key: 'output', label: '模型产出', step: '③' },
];

async function renderPipelineTab() {
  const el = document.getElementById('subtab-content');
  el.innerHTML = '<div class="text-xs text-gray-400 py-8 text-center">加载中...</div>';

  try {
    const res = await api(`/models/${currentModelId}/pipeline`);
    if (!res.exists) {
      renderPipelineEmpty(el);
    } else if (pipelineEditMode) {
      renderPipelineEditor(el, res.content);
    } else {
      renderPipelineView(el, res.content, res.data);
    }
  } catch (e) {
    el.innerHTML = `<div class="text-xs text-red-500 py-8 text-center">${e.message}</div>`;
  }
}

function renderPipelineEmpty(el) {
  el.innerHTML = `
    <div class="text-center py-16">
      <div class="text-gray-300 text-5xl mb-4">&#9881;</div>
      <h3 class="text-lg font-medium text-gray-700 mb-2">尚未定义训练流水线</h3>
      <p class="text-sm text-gray-500 mb-6">定义流水线可规范训练过程，为后续自动化训练打基础</p>
      <button onclick="pipelineEditMode=true;renderPipelineEditor(document.getElementById('subtab-content'),PIPELINE_TEMPLATE)"
        class="px-4 py-2 bg-brand-600 text-white text-sm rounded-lg hover:bg-brand-700">
        + 创建流水线定义
      </button>
    </div>
  `;
}

function renderPipelineView(el, content, data) {
  // Build pipeline stage cards from actual data
  const stageCards = pipelineStagesMeta.map((s, i) => {
    const stageData = data[s.key] || {};
    const entries = Object.entries(stageData);
    const kvHtml = entries.length
      ? entries.map(([k, v]) => {
          const display = Array.isArray(v) ? v.join(', ') : String(v);
          return `<div class="text-[10px] text-gray-500 truncate"><span class="text-gray-400">${k}:</span> ${escapeHtml(display)}</div>`;
        }).join('')
      : '<div class="text-[10px] text-gray-400 italic">未定义</div>';
    return `
      ${i > 0 ? '<div class="flex items-center px-2 text-gray-300 text-lg flex-shrink-0">→</div>' : ''}
      <div class="flex-1 p-3 rounded-lg border bg-white">
        <div class="text-xs font-semibold text-gray-700 mb-1">${s.step} ${s.label}</div>
        ${kvHtml}
      </div>
    `;
  }).join('');

  // Build version options for run dialog
  const versionOptions = (currentModelVersions || [])
    .filter(v => v.stage !== 'draft')
    .map(v => `<option value="${v.version}">${fmtVer(v.version)}</option>`).join('');

  el.innerHTML = `
    <div class="space-y-6">
      <div class="flex items-center justify-between">
        <h3 class="text-sm font-medium text-gray-700">流水线定义</h3>
        <div class="flex gap-2">
          <button onclick="showRunDialog()"
            class="px-3 py-1.5 text-xs rounded-lg bg-green-600 text-white hover:bg-green-700">运行训练</button>
          <button onclick="pipelineEditMode=true;renderPipelineEditor(document.getElementById('subtab-content'),document.getElementById('pipeline-yaml-src').textContent)"
            class="px-3 py-1.5 text-xs rounded-lg border hover:bg-gray-50">编辑</button>
          <button onclick="deletePipeline()"
            class="px-3 py-1.5 text-xs rounded-lg border border-red-200 text-red-600 hover:bg-red-50">删除</button>
        </div>
      </div>
      <div class="flex items-stretch gap-0 p-4 bg-gray-50 rounded-xl">
        ${stageCards}
      </div>

      <!-- Run dialog (hidden by default) -->
      <div id="run-dialog" class="hidden border rounded-lg p-4 bg-blue-50 border-blue-200">
        <h4 class="text-sm font-medium text-gray-700 mb-3">启动训练运行</h4>
        <div class="flex items-end gap-3 mb-3">
          <div class="flex-1">
            <label class="block text-xs text-gray-500 mb-1">基础版本（复制其数据和配置）</label>
            <select id="run-base-version" class="w-full px-3 py-2 border rounded-lg text-sm bg-white">
              ${versionOptions}
            </select>
          </div>
        </div>
        <details class="mb-3">
          <summary class="text-xs text-gray-500 cursor-pointer hover:text-gray-700">参数覆写（可选）</summary>
          <div class="grid grid-cols-3 gap-2 mt-2">
            <div>
              <label class="block text-[10px] text-gray-400 mb-0.5">dataset</label>
              <input id="run-override-dataset" type="text" placeholder="如 data_v2.csv"
                class="w-full px-2 py-1.5 border rounded text-xs bg-white" />
            </div>
            <div>
              <label class="block text-[10px] text-gray-400 mb-0.5">feature_config</label>
              <input id="run-override-feature" type="text" placeholder="如 features_v2.yaml"
                class="w-full px-2 py-1.5 border rounded text-xs bg-white" />
            </div>
            <div>
              <label class="block text-[10px] text-gray-400 mb-0.5">params</label>
              <input id="run-override-params" type="text" placeholder="如 hp_tuned.yaml"
                class="w-full px-2 py-1.5 border rounded text-xs bg-white" />
            </div>
          </div>
        </details>
        <div class="flex justify-end gap-2">
          <button onclick="document.getElementById('run-dialog').classList.add('hidden')" class="px-4 py-2 text-sm text-gray-600 hover:bg-gray-100 rounded-lg">取消</button>
          <button onclick="startPipelineRun()" class="px-4 py-2 bg-green-600 text-white text-sm rounded-lg hover:bg-green-700">开始运行</button>
        </div>
      </div>

      <!-- Active run panel -->
      <div id="run-active-panel"></div>

      <!-- Run history -->
      <div id="run-history"></div>

      <div class="rounded-lg overflow-hidden border">
        <div class="bg-gray-100 px-3 py-1.5 text-xs text-gray-500 border-b">pipeline.yaml</div>
        <pre class="!m-0 !rounded-none"><code class="language-yaml">${escapeHtml(content)}</code></pre>
      </div>
      <script type="text/plain" id="pipeline-yaml-src">${escapeHtml(content)}</script>
    </div>
  `;
  el.querySelectorAll('pre code').forEach(block => hljs.highlightElement(block));

  // Load run history
  loadRunHistory();
}

function renderPipelineEditor(el, content) {
  el.innerHTML = `
    <div class="space-y-4">
      <h3 class="text-sm font-medium text-gray-700">编辑流水线定义</h3>
      <div>
        <textarea id="pipeline-editor" rows="16"
          class="w-full px-4 py-3 border rounded-lg text-sm font-mono bg-gray-50 focus:ring-2 focus:ring-brand-500 focus:border-transparent outline-none"
          spellcheck="false">${escapeHtml(content)}</textarea>
        <div id="pipeline-error" class="hidden mt-2 text-xs text-red-600 bg-red-50 rounded-lg px-3 py-2"></div>
      </div>
      <div class="flex justify-end gap-3">
        <button onclick="pipelineEditMode=false;renderPipelineTab()"
          class="px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 rounded-lg">取消</button>
        <button onclick="savePipeline()"
          class="px-4 py-2 bg-brand-600 text-white text-sm rounded-lg hover:bg-brand-700">保存</button>
      </div>
    </div>
  `;
}

async function savePipeline() {
  const content = document.getElementById('pipeline-editor').value;
  const errEl = document.getElementById('pipeline-error');

  try {
    await api(`/models/${currentModelId}/pipeline`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content }),
    });
    pipelineEditMode = false;
    showToast('流水线定义已保存');
    renderPipelineTab();
  } catch (e) {
    errEl.textContent = e.message;
    errEl.classList.remove('hidden');
  }
}

async function deletePipeline() {
  if (!confirm('确定删除流水线定义？')) return;
  try {
    await api(`/models/${currentModelId}/pipeline`, { method: 'DELETE' });
    showToast('流水线定义已删除');
    renderPipelineTab();
  } catch (e) {
    showToast(e.message, 'error');
  }
}

// ── Pipeline Run Execution ──

let activeRunId = null;
let runPollTimer = null;

function showRunDialog() {
  const dialog = document.getElementById('run-dialog');
  if (dialog) dialog.classList.remove('hidden');
}

async function startPipelineRun() {
  const sel = document.getElementById('run-base-version');
  if (!sel || !sel.value) { showToast('请选择基础版本', 'error'); return; }

  const baseVersion = sel.value;
  document.getElementById('run-dialog').classList.add('hidden');

  // Collect overrides
  const overrides = {};
  const ds = (document.getElementById('run-override-dataset') || {}).value;
  const fc = (document.getElementById('run-override-feature') || {}).value;
  const pr = (document.getElementById('run-override-params') || {}).value;
  if (ds && ds.trim()) overrides.dataset = ds.trim();
  if (fc && fc.trim()) overrides.feature_config = fc.trim();
  if (pr && pr.trim()) overrides.params = pr.trim();

  const body = { base_version: baseVersion };
  if (Object.keys(overrides).length) body.overrides = overrides;

  try {
    const run = await api(`/models/${currentModelId}/pipeline/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    activeRunId = run.id;
    showToast('训练运行已启动');
    renderRunActivePanel(run);
    startRunPolling();
  } catch (e) {
    showToast(e.message, 'error');
  }
}

function renderRunActivePanel(run) {
  const panel = document.getElementById('run-active-panel');
  if (!panel) return;

  const statusColors = {
    pending: 'bg-yellow-100 text-yellow-700 border-yellow-300',
    running: 'bg-blue-100 text-blue-700 border-blue-300',
    success: 'bg-green-100 text-green-700 border-green-300',
    failed: 'bg-red-100 text-red-700 border-red-300',
  };
  const statusLabels = { pending: '准备中', running: '运行中', success: '已完成', failed: '失败' };
  const sc = statusColors[run.status] || statusColors.pending;
  const sl = statusLabels[run.status] || run.status;

  const logHtml = run.log
    ? `<pre class="mt-3 p-3 bg-gray-900 text-green-400 text-[11px] font-mono rounded-lg max-h-64 overflow-y-auto whitespace-pre-wrap">${escapeHtml(run.log)}</pre>`
    : '<div class="mt-3 text-xs text-gray-400 italic">等待日志输出...</div>';

  const metricsHtml = run.metrics
    ? `<div class="mt-3 grid grid-cols-3 gap-2">${Object.entries(run.metrics).map(([k, v]) =>
        `<div class="text-center p-2 bg-white rounded border"><div class="text-[10px] text-gray-400">${k}</div><div class="text-sm font-semibold text-gray-700">${typeof v === 'number' ? v.toFixed(4) : v}</div></div>`
      ).join('')}</div>`
    : '';

  const resultHtml = run.result_version
    ? `<div class="mt-2 text-xs text-green-700">新版本: <span class="font-semibold">${run.result_version}</span></div>`
    : '';

  panel.innerHTML = `
    <div class="border rounded-lg p-4 ${sc}">
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-2">
          <span class="text-sm font-medium">${sl}</span>
          ${run.status === 'running' ? '<span class="inline-block w-2 h-2 bg-blue-500 rounded-full animate-pulse"></span>' : ''}
        </div>
        <div class="text-[10px] text-gray-500">
          ${run.base_version} → ${run.target_version || '...'}
          ${run.finished_at ? ' | ' + formatTime(run.finished_at) : ''}
        </div>
      </div>
      ${resultHtml}
      ${metricsHtml}
      ${logHtml}
    </div>
  `;

  // Auto-scroll log
  const logEl = panel.querySelector('pre');
  if (logEl) logEl.scrollTop = logEl.scrollHeight;
}

function startRunPolling() {
  stopRunPolling();
  runPollTimer = setInterval(pollRunStatus, 2000);
}

function stopRunPolling() {
  if (runPollTimer) { clearInterval(runPollTimer); runPollTimer = null; }
}

async function pollRunStatus() {
  if (!activeRunId || !currentModelId) { stopRunPolling(); return; }
  try {
    const run = await api(`/models/${currentModelId}/pipeline/runs/${activeRunId}`);
    renderRunActivePanel(run);
    if (run.status === 'success' || run.status === 'failed') {
      stopRunPolling();
      activeRunId = null;
      loadRunHistory();
      if (run.status === 'success') {
        // Refresh version list
        currentModelVersions = await api(`/models/${currentModelId}/versions`);
      }
    }
  } catch (e) {
    stopRunPolling();
  }
}

async function loadRunHistory() {
  const el = document.getElementById('run-history');
  if (!el) return;

  try {
    const runs = await api(`/models/${currentModelId}/pipeline/runs`);
    if (!runs.length) { el.innerHTML = ''; return; }

    const statusIcons = { pending: '&#9711;', running: '&#9881;', success: '&#10003;', failed: '&#10007;' };
    const statusColors = { pending: 'text-yellow-500', running: 'text-blue-500', success: 'text-green-600', failed: 'text-red-500' };

    el.innerHTML = `
      <div class="border rounded-lg overflow-hidden">
        <div class="bg-gray-50 px-3 py-2 text-xs font-medium text-gray-600 border-b">运行历史</div>
        <div class="divide-y">
          ${runs.map(r => `
            <div class="px-3 py-2 flex items-center justify-between text-xs hover:bg-gray-50 cursor-pointer" onclick="viewRunDetail('${r.id}')">
              <div class="flex items-center gap-2">
                <span class="${statusColors[r.status] || 'text-gray-400'}">${statusIcons[r.status] || '?'}</span>
                <span class="text-gray-700">${r.base_version} → ${r.target_version || '...'}</span>
              </div>
              <div class="flex items-center gap-3">
                ${r.result_version ? `<span class="text-green-600 font-medium">${r.result_version}</span>` : ''}
                <span class="text-gray-400">${formatTime(r.started_at)}</span>
              </div>
            </div>
          `).join('')}
        </div>
      </div>
    `;
  } catch (e) {
    el.innerHTML = '';
  }
}

async function viewRunDetail(runId) {
  try {
    const run = await api(`/models/${currentModelId}/pipeline/runs/${runId}`);
    activeRunId = null;
    renderRunActivePanel(run);
    if (run.status === 'running' || run.status === 'pending') {
      activeRunId = run.id;
      startRunPolling();
    }
  } catch (e) {
    showToast(e.message, 'error');
  }
}

// ── Fork ──

function showForkDialog() {
  const versions = currentModelVersions || [];
  const vOpts = versions.map(v =>
    `<option value="${v.id}">${fmtVer(v.version)}</option>`
  ).join('');
  const m = currentModelData;

  const html = `
    <div class="fixed inset-0 z-50 flex items-center justify-center bg-black/30" id="fork-overlay" onclick="if(event.target===this)this.remove()">
      <div class="bg-white rounded-xl shadow-xl w-full max-w-md p-6" onclick="event.stopPropagation()">
        <h3 class="text-base font-semibold text-gray-800 mb-4">\u2442 Fork 模型</h3>
        <p class="text-xs text-gray-500 mb-4">从 <strong>${escapeHtml(m.name)}</strong> 的版本创建新模型</p>
        <div class="space-y-3">
          <div>
            <label class="block text-xs text-gray-600 mb-1">源版本</label>
            <select id="fork-source-version" class="w-full px-3 py-2 border rounded-lg text-sm bg-white">${vOpts}</select>
          </div>
          <div>
            <label class="block text-xs text-gray-600 mb-1">新模型名称</label>
            <input id="fork-new-name" type="text" placeholder="如: 华南短期负荷预测模型-GBR-v1"
              class="w-full px-3 py-2 border rounded-lg text-sm" />
          </div>
          <div>
            <label class="block text-xs text-gray-600 mb-1">所属单位</label>
            <input id="fork-new-org" type="text" placeholder="如: 华南电网"
              class="w-full px-3 py-2 border rounded-lg text-sm" />
          </div>
          <div>
            <label class="block text-xs text-gray-600 mb-1">描述（可选）</label>
            <input id="fork-desc" type="text" placeholder="Fork 用途说明"
              class="w-full px-3 py-2 border rounded-lg text-sm" />
          </div>
        </div>
        <div class="flex justify-end gap-2 mt-5">
          <button onclick="document.getElementById('fork-overlay').remove()"
            class="px-4 py-2 text-sm text-gray-600 hover:bg-gray-100 rounded-lg">取消</button>
          <button onclick="forkModel()"
            class="px-4 py-2 bg-indigo-600 text-white text-sm rounded-lg hover:bg-indigo-700">确认 Fork</button>
        </div>
      </div>
    </div>
  `;
  document.body.insertAdjacentHTML('beforeend', html);
}

async function forkModel() {
  const versionId = document.getElementById('fork-source-version').value;
  const newName = document.getElementById('fork-new-name').value.trim();
  const newOrg = document.getElementById('fork-new-org').value.trim();
  const desc = document.getElementById('fork-desc').value.trim();

  if (!newName) { showToast('请输入新模型名称', 'error'); return; }
  if (!newOrg) { showToast('请输入所属单位', 'error'); return; }

  try {
    const result = await api(`/models/${currentModelId}/fork`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        source_version_id: versionId,
        new_name: newName,
        new_owner_org: newOrg,
        description: desc || undefined,
      }),
    });
    document.getElementById('fork-overlay').remove();
    showToast('Fork 成功！新模型已创建');
    // Navigate to new model
    openModelDetail(result.id);
  } catch (e) {
    showToast(e.message, 'error');
  }
}

// ── Artifact Management ──

function invalidateArtifactCache(versionId) {
  Object.keys(artifactTabCache).forEach(key => {
    if (key.startsWith(versionId + ':')) delete artifactTabCache[key];
  });
}

function reloadCurrentStage(versionId) {
  if (expandedVersionId === versionId && activePipelineStage) {
    loadPipelineStage(versionId, activePipelineStage);
  }
}

// ── Draft Version Functions ──

function showCreateDraftDialog() {
  const versions = (currentModelVersions || []).filter(v => v.stage !== 'draft');
  if (!versions.length) {
    showToast('需要至少一个已有版本作为基础', 'error');
    return;
  }
  const vOpts = versions.map(v =>
    `<option value="${v.version}">${fmtVer(v.version)}</option>`
  ).join('');
  const html = `
    <div class="fixed inset-0 z-50 flex items-center justify-center bg-black/30"
         id="draft-overlay" onclick="if(event.target===this)this.remove()">
      <div class="bg-white rounded-xl shadow-xl w-full max-w-md p-6" onclick="event.stopPropagation()">
        <h3 class="text-base font-semibold text-gray-800 mb-4">准备新版本（草稿）</h3>
        <p class="text-xs text-gray-500 mb-4">从已有版本复制数据和配置，您可以在训练前修改各项文件</p>
        <div class="space-y-3">
          <div>
            <label class="block text-xs text-gray-600 mb-1">基础版本</label>
            <select id="draft-base-version" class="w-full px-3 py-2 border rounded-lg text-sm bg-white">${vOpts}</select>
          </div>
          <div>
            <label class="block text-xs text-gray-600 mb-1">说明（可选）</label>
            <input id="draft-description" type="text" placeholder="如：调整特征后重新训练"
              class="w-full px-3 py-2 border rounded-lg text-sm" />
          </div>
        </div>
        <div class="flex justify-end gap-2 mt-5">
          <button onclick="document.getElementById('draft-overlay').remove()"
            class="px-4 py-2 text-sm text-gray-600 hover:bg-gray-100 rounded-lg">取消</button>
          <button onclick="createDraftVersion()"
            class="px-4 py-2 bg-amber-500 text-white text-sm rounded-lg hover:bg-amber-600">创建草稿</button>
        </div>
      </div>
    </div>`;
  document.body.insertAdjacentHTML('beforeend', html);
}

async function createDraftVersion() {
  const baseVersion = document.getElementById('draft-base-version').value;
  const desc = (document.getElementById('draft-description') || {}).value || '';
  try {
    const result = await api(`/models/${currentModelId}/versions/draft`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ base_version: baseVersion, description: desc || undefined }),
    });
    document.getElementById('draft-overlay').remove();
    showToast(`草稿版本 ${fmtVer(result.version)} 已创建`);
    currentModelVersions = await api(`/models/${currentModelId}/versions`);
    expandedVersionId = result.id;
    activePipelineStage = 'data_prep';
    artifactTabCache = {};
    renderVersionsTab();
  } catch (e) { showToast(e.message, 'error'); }
}

async function startDraftTraining(draftVersion) {
  try {
    const pipeline = await api(`/models/${currentModelId}/pipeline`);
    if (!pipeline.exists) {
      showToast('请先在「流水线」标签页定义训练流水线', 'error');
      return;
    }
  } catch (e) {
    showToast('无法获取流水线定义: ' + e.message, 'error');
    return;
  }
  if (!confirm(`确定开始训练草稿版本 ${fmtVer(draftVersion)}？`)) return;
  try {
    const run = await api(`/models/${currentModelId}/pipeline/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ base_version: draftVersion, draft_version: draftVersion }),
    });
    showToast('草稿版本训练已启动');
    currentSubTab = 'pipeline';
    activeRunId = run.id;
    switchSubTab('pipeline');
    startRunPolling();
  } catch (e) { showToast(e.message, 'error'); }
}

async function archiveDraft(versionId) {
  if (!confirm('确定废弃此草稿版本？此操作不可撤销。')) return;
  try {
    await api(`/models/${currentModelId}/versions/${versionId}/stage`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ target_stage: 'archived' }),
    });
    showToast('草稿已废弃');
    currentModelVersions = await api(`/models/${currentModelId}/versions`);
    expandedVersionId = null;
    renderVersionsTab();
  } catch (e) { showToast(e.message, 'error'); }
}

function showUploadArtifact(versionId, category) {
  const categoryLabels = {
    datasets: '数据集', features: '特征定义', code: '训练代码', params: '超参数'
  };
  const html = `
    <div class="fixed inset-0 z-50 flex items-center justify-center bg-black/30"
         id="upload-artifact-overlay" onclick="if(event.target===this)this.remove()">
      <div class="bg-white rounded-xl shadow-xl w-full max-w-md p-6" onclick="event.stopPropagation()">
        <h3 class="text-base font-semibold text-gray-800 mb-4">上传文件到 ${categoryLabels[category] || category}</h3>
        <form id="form-upload-artifact" onsubmit="uploadArtifact(event,'${versionId}','${category}')">
          <input type="file" name="file" required
            class="w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-medium file:bg-brand-50 file:text-brand-700 hover:file:bg-brand-100 mb-4">
          <p class="text-xs text-gray-400 mb-4">最大 50 MB。上传同名文件将覆盖原文件。</p>
          <div class="flex justify-end gap-2">
            <button type="button" onclick="document.getElementById('upload-artifact-overlay').remove()"
              class="px-4 py-2 text-sm text-gray-600 hover:bg-gray-100 rounded-lg">取消</button>
            <button type="submit"
              class="px-4 py-2 bg-brand-600 text-white text-sm rounded-lg hover:bg-brand-700">上传</button>
          </div>
        </form>
      </div>
    </div>
  `;
  document.body.insertAdjacentHTML('beforeend', html);
}

async function uploadArtifact(e, versionId, category) {
  e.preventDefault();
  const fd = new FormData(e.target);
  try {
    const res = await fetch(
      API + `/models/${currentModelId}/versions/${versionId}/artifacts/${category}`,
      { method: 'POST', body: fd }
    );
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || JSON.stringify(err));
    }
    document.getElementById('upload-artifact-overlay').remove();
    showToast('文件上传成功');
    invalidateArtifactCache(versionId);
    reloadCurrentStage(versionId);
  } catch (err) {
    showToast(err.message, 'error');
  }
}

async function editArtifact(versionId, category, filename) {
  try {
    const res = await fetch(
      API + `/models/${currentModelId}/versions/${versionId}/artifacts/${category}/${filename}`
    );
    if (!res.ok) throw new Error('Failed to load file');
    const text = await res.text();

    const html = `
      <div class="fixed inset-0 z-50 flex items-center justify-center bg-black/30"
           id="edit-artifact-overlay" onclick="if(event.target===this)this.remove()">
        <div class="bg-white rounded-xl shadow-xl w-full max-w-2xl mx-4 max-h-[90vh] flex flex-col"
             onclick="event.stopPropagation()">
          <div class="flex items-center justify-between px-6 py-4 border-b">
            <h3 class="text-base font-semibold text-gray-800">编辑 ${escapeHtml(filename)}</h3>
            <button onclick="document.getElementById('edit-artifact-overlay').remove()"
              class="text-gray-400 hover:text-gray-600 text-xl">&times;</button>
          </div>
          <div class="flex-1 p-4 overflow-hidden">
            <textarea id="edit-artifact-content"
              class="w-full h-full min-h-[300px] px-3 py-2 border rounded-lg text-sm font-mono resize-y"
              spellcheck="false">${escapeHtml(text)}</textarea>
          </div>
          <div class="flex justify-end gap-2 px-6 py-4 border-t">
            <button onclick="document.getElementById('edit-artifact-overlay').remove()"
              class="px-4 py-2 text-sm text-gray-600 hover:bg-gray-100 rounded-lg">取消</button>
            <button onclick="saveArtifact('${versionId}','${category}','${filename}')"
              class="px-4 py-2 bg-brand-600 text-white text-sm rounded-lg hover:bg-brand-700">保存</button>
          </div>
        </div>
      </div>
    `;
    document.body.insertAdjacentHTML('beforeend', html);
  } catch (err) {
    showToast(err.message, 'error');
  }
}

async function saveArtifact(versionId, category, filename) {
  const content = document.getElementById('edit-artifact-content').value;
  try {
    await api(`/models/${currentModelId}/versions/${versionId}/artifacts/${category}/${filename}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content }),
    });
    document.getElementById('edit-artifact-overlay').remove();
    showToast('文件已保存');
    invalidateArtifactCache(versionId);
    reloadCurrentStage(versionId);
  } catch (err) {
    showToast(err.message, 'error');
  }
}

async function deleteArtifact(versionId, category, filename) {
  if (!confirm('确定要删除 ' + filename + ' 吗？此操作不可撤销。')) return;
  try {
    const res = await fetch(
      API + `/models/${currentModelId}/versions/${versionId}/artifacts/${category}/${filename}`,
      { method: 'DELETE' }
    );
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || JSON.stringify(err));
    }
    showToast('文件已删除');
    invalidateArtifactCache(versionId);
    reloadCurrentStage(versionId);
  } catch (err) {
    showToast(err.message, 'error');
  }
}

// ── Sub-tab: Deploy & Predict ──

async function renderDeployTab() {
  const el = document.getElementById('subtab-content');
  el.innerHTML = '<div class="text-sm text-gray-400 py-8 text-center">加载中...</div>';

  try {
    // Get all deployments for this model's versions
    const versions = currentModelVersions;
    const versionIds = new Set(versions.map(v => v.id));

    const allDeploys = await api('/deployments');
    const deploys = allDeploys.filter(d => versionIds.has(d.model_version_id));

    // Build version lookup
    const versionMap = {};
    for (const v of versions) {
      versionMap[v.id] = v.version;
    }

    el.innerHTML = `
      <div class="space-y-4">
        <div class="flex items-center justify-between">
          <h3 class="text-sm font-medium text-gray-700">部署列表 (${deploys.length})</h3>
          <button onclick="showCreateDeployForModel()" class="px-3 py-1.5 bg-brand-600 text-white text-xs rounded-lg hover:bg-brand-700">+ 新建部署</button>
        </div>
        ${deploys.length ? deploys.map(d => {
          const endpointUrl = location.origin + API + '/predict/' + encodeURIComponent(d.name);
          const endpointById = location.origin + API + '/deployments/' + d.id + '/predict';
          return `
          <div class="bg-white rounded-xl border p-5">
            <div class="flex items-center justify-between mb-3">
              <div class="flex items-center gap-3">
                <h4 class="font-medium text-sm">${d.name}</h4>
                ${badge(d.status)}
                <span class="text-xs text-gray-400">${fmtVer(versionMap[d.model_version_id] || '?')}</span>
              </div>
              <div class="flex gap-2">
                ${d.status === 'pending' || d.status === 'stopped' ? `<button onclick="deployAction('${d.id}','start')" class="px-3 py-1 bg-green-600 text-white text-xs rounded-lg hover:bg-green-700">启动</button>` : ''}
                ${d.status === 'running' ? `<button onclick="deployAction('${d.id}','stop')" class="px-3 py-1 bg-yellow-600 text-white text-xs rounded-lg hover:bg-yellow-700">停止</button>` : ''}
                ${d.status === 'running' ? `<button onclick="openPredict('${d.id}')" class="px-3 py-1 bg-brand-600 text-white text-xs rounded-lg hover:bg-brand-700">推理</button>` : ''}
                <button onclick="deleteDeploy('${d.id}')" class="px-3 py-1 bg-gray-100 text-gray-600 text-xs rounded-lg hover:bg-gray-200">删除</button>
              </div>
            </div>
            ${d.status === 'running' ? `
            <div class="mt-3 bg-gray-50 rounded-lg p-4 border border-gray-200">
              <div class="flex items-center justify-between mb-2">
                <span class="text-xs font-medium text-gray-600">API 端点</span>
                <button onclick="copyEndpoint('${endpointUrl}')" class="text-xs text-brand-600 hover:text-brand-700">复制 URL</button>
              </div>
              <code class="block text-xs text-gray-800 bg-white px-3 py-1.5 rounded border mb-3 break-all">${endpointUrl}</code>
              <details class="group">
                <summary class="text-xs text-gray-500 cursor-pointer hover:text-gray-700">调用示例</summary>
                <div class="mt-2 space-y-2">
                  <div>
                    <div class="text-xs text-gray-400 mb-1">curl</div>
                    <pre class="text-xs bg-gray-900 text-green-300 p-3 rounded-lg overflow-x-auto">curl -X POST ${endpointUrl} \\
  -H "Content-Type: application/json" \\
  -d '{"input_data": [[25.0, 60.0, 14, 1, 0, 7]]}'</pre>
                  </div>
                  <div>
                    <div class="text-xs text-gray-400 mb-1">Python</div>
                    <pre class="text-xs bg-gray-900 text-green-300 p-3 rounded-lg overflow-x-auto">import requests

resp = requests.post(
    "${endpointUrl}",
    json={"input_data": [[25.0, 60.0, 14, 1, 0, 7]]}
)
print(resp.json())</pre>
                  </div>
                </div>
              </details>
            </div>` : ''}
            <div class="text-xs text-gray-400 mt-3">
              创建: ${formatTime(d.created_at)}
              ${d.error_message ? `<span class="text-red-500 ml-2">${d.error_message}</span>` : ''}
            </div>
          </div>`;
        }).join('') : '<div class="text-sm text-gray-400 py-12 text-center bg-white rounded-xl border">暂无部署</div>'}
      </div>
    `;
  } catch (e) {
    el.innerHTML = `<div class="text-sm text-red-500 py-8 text-center">${e.message}</div>`;
  }
}

function showCreateDeployForModel() {
  const versions = currentModelVersions;
  const sel = document.getElementById('deploy-version-select');
  sel.innerHTML = '<option value="">请选择...</option>' +
    versions.map(v => `<option value="${v.id}">${currentModelData.name} / ${fmtVer(v.version)} (${v.stage})</option>`).join('');
  showModal('deploy-create');
}

async function createDeploy(e) {
  e.preventDefault();
  const fd = new FormData(e.target);
  try {
    await api('/deployments', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: fd.get('name'),
        model_version_id: fd.get('model_version_id'),
      }),
    });
    showToast('部署创建成功');
    hideModal('deploy-create');
    e.target.reset();
    if (currentSubTab === 'deploy') renderDeployTab();
  } catch (err) { showToast(err.message, 'error'); }
}

async function deployAction(id, action) {
  try {
    await api('/deployments/' + id + '/' + action, { method: 'POST' });
    showToast(action === 'start' ? '已启动' : '已停止');
    if (currentSubTab === 'deploy') renderDeployTab();
  } catch (e) { showToast(e.message, 'error'); }
}

async function deleteDeploy(id) {
  if (!confirm('确定删除此部署？')) return;
  try {
    await api('/deployments/' + id, { method: 'DELETE' });
    showToast('已删除');
    if (currentSubTab === 'deploy') renderDeployTab();
  } catch (e) { showToast(e.message, 'error'); }
}

function copyEndpoint(url) {
  navigator.clipboard.writeText(url).then(
    () => showToast('已复制到剪贴板'),
    () => showToast('复制失败', 'error')
  );
}

function openPredict(deployId) {
  document.getElementById('predict-deploy-id').value = deployId;
  document.getElementById('predict-result').classList.add('hidden');
  document.getElementById('predict-input').value = '{"input_data": [[25.0, 60.0, 14, 1, 0, 7]]}';
  showModal('predict');
}

async function runPredict() {
  const deployId = document.getElementById('predict-deploy-id').value;
  const input = document.getElementById('predict-input').value;
  try {
    const body = JSON.parse(input);
    const res = await api('/deployments/' + deployId + '/predict', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    document.getElementById('predict-output').textContent = JSON.stringify(res, null, 2);
    document.getElementById('predict-result').classList.remove('hidden');
  } catch (e) {
    showToast(e.message, 'error');
  }
}

// ── Sub-tab: Monitor ──

let monitorDeployId = null;

async function renderMonitorTab() {
  const el = document.getElementById('subtab-content');
  el.innerHTML = '<div class="text-sm text-gray-400 py-8 text-center">加载中...</div>';

  try {
    const versions = currentModelVersions;
    const versionIds = new Set(versions.map(v => v.id));
    const allDeploys = await api('/deployments');
    const deploys = allDeploys.filter(d => versionIds.has(d.model_version_id));

    // Auto-select first deployment if available
    if (!monitorDeployId || !deploys.find(d => d.id === monitorDeployId)) {
      monitorDeployId = deploys.length ? deploys[0].id : null;
    }

    el.innerHTML = `
      <div class="space-y-6">
        <div class="flex gap-3 items-end">
          <div>
            <label class="block text-xs text-gray-500 mb-1">选择部署</label>
            <select id="monitor-deploy-select" class="px-3 py-2 border rounded-lg text-sm bg-white" onchange="onMonitorDeployChange()">
              ${!deploys.length ? '<option value="">无可用部署</option>' : ''}
              ${deploys.map(d => `<option value="${d.id}" ${d.id === monitorDeployId ? 'selected' : ''}>${d.name} (${d.status})</option>`).join('')}
            </select>
          </div>
          <button onclick="loadMonitorData()" class="px-4 py-2 bg-gray-100 text-sm rounded-lg hover:bg-gray-200">刷新</button>
        </div>
        <div id="monitor-stats" class="grid grid-cols-2 md:grid-cols-5 gap-4"></div>
        <div id="monitor-metrics"></div>
        <div>
          <h3 class="text-sm font-medium text-gray-700 mb-3">预测日志</h3>
          <div class="bg-white rounded-xl border overflow-hidden">
            <table class="w-full text-sm">
              <thead class="bg-gray-50">
                <tr>
                  <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">时间</th>
                  <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">输入</th>
                  <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">输出</th>
                  <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">真实值</th>
                  <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">延迟</th>
                </tr>
              </thead>
              <tbody id="prediction-log-body" class="divide-y divide-gray-100"></tbody>
            </table>
          </div>
        </div>
      </div>
    `;

    if (monitorDeployId) loadMonitorData();
  } catch (e) {
    el.innerHTML = `<div class="text-sm text-red-500 py-8 text-center">${e.message}</div>`;
  }
}

function onMonitorDeployChange() {
  monitorDeployId = document.getElementById('monitor-deploy-select').value;
  loadMonitorData();
}

async function loadMonitorData() {
  if (!monitorDeployId) {
    document.getElementById('monitor-stats').innerHTML = '';
    document.getElementById('monitor-metrics').innerHTML = '';
    document.getElementById('prediction-log-body').innerHTML = '';
    return;
  }

  try {
    const [stats, metrics, logs] = await Promise.all([
      api('/deployments/' + monitorDeployId + '/stats'),
      api('/deployments/' + monitorDeployId + '/metrics'),
      api('/deployments/' + monitorDeployId + '/predictions?limit=50'),
    ]);

    document.getElementById('monitor-stats').innerHTML = `
      <div class="bg-white rounded-xl border p-4">
        <div class="text-xs text-gray-500">总预测量</div>
        <div class="text-2xl font-semibold mt-1">${stats.total_predictions}</div>
      </div>
      <div class="bg-white rounded-xl border p-4">
        <div class="text-xs text-gray-500">平均延迟</div>
        <div class="text-2xl font-semibold mt-1">${stats.avg_latency_ms.toFixed(2)}<span class="text-sm text-gray-400 ml-1">ms</span></div>
      </div>
      <div class="bg-white rounded-xl border p-4">
        <div class="text-xs text-gray-500">P95 延迟</div>
        <div class="text-2xl font-semibold mt-1">${stats.p95_latency_ms.toFixed(2)}<span class="text-sm text-gray-400 ml-1">ms</span></div>
      </div>
      <div class="bg-white rounded-xl border p-4">
        <div class="text-xs text-gray-500">错误率</div>
        <div class="text-2xl font-semibold mt-1 ${stats.error_rate > 0 ? 'text-red-600' : 'text-green-600'}">${(stats.error_rate * 100).toFixed(1)}%</div>
      </div>
      <div class="bg-white rounded-xl border p-4">
        <div class="text-xs text-gray-500">有真实值</div>
        <div class="text-2xl font-semibold mt-1">${metrics.count}</div>
      </div>
    `;

    if (metrics.count > 0) {
      document.getElementById('monitor-metrics').innerHTML = `
        <h3 class="text-sm font-medium text-gray-700 mb-3">精度指标</h3>
        <div class="grid grid-cols-3 gap-4">
          <div class="bg-white rounded-xl border p-4 text-center">
            <div class="text-xs text-gray-500">MAE</div>
            <div class="text-xl font-semibold mt-1">${metrics.mae?.toFixed(2) ?? '-'}<span class="text-sm text-gray-400 ml-1">MW</span></div>
          </div>
          <div class="bg-white rounded-xl border p-4 text-center">
            <div class="text-xs text-gray-500">RMSE</div>
            <div class="text-xl font-semibold mt-1">${metrics.rmse?.toFixed(2) ?? '-'}<span class="text-sm text-gray-400 ml-1">MW</span></div>
          </div>
          <div class="bg-white rounded-xl border p-4 text-center">
            <div class="text-xs text-gray-500">MAPE</div>
            <div class="text-xl font-semibold mt-1">${metrics.mape?.toFixed(2) ?? '-'}<span class="text-sm text-gray-400 ml-1">%</span></div>
          </div>
        </div>
      `;
    } else {
      document.getElementById('monitor-metrics').innerHTML = '';
    }

    document.getElementById('prediction-log-body').innerHTML = logs.length
      ? logs.map(l => `
        <tr class="hover:bg-gray-50">
          <td class="px-4 py-2 text-xs text-gray-500 whitespace-nowrap">${formatTime(l.created_at)}</td>
          <td class="px-4 py-2 text-xs font-mono max-w-[180px] truncate" title='${JSON.stringify(l.input_data)}'>${truncJson(l.input_data, 40)}</td>
          <td class="px-4 py-2 text-xs font-mono">${truncJson(l.output_data, 30)}</td>
          <td class="px-4 py-2 text-xs font-mono">${l.actual_value ? truncJson(l.actual_value, 20) : '<span class="text-gray-300">-</span>'}</td>
          <td class="px-4 py-2 text-xs text-gray-500">${l.latency_ms.toFixed(2)} ms</td>
        </tr>
      `).join('')
      : '<tr><td colspan="5" class="px-4 py-8 text-center text-gray-400 text-sm">暂无预测记录</td></tr>';
  } catch (e) { showToast(e.message, 'error'); }
}

// ── Trial Evaluation ──

function showTrialEvaluate(versionId) {
  const html = `
    <div class="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4"
         id="trial-eval-overlay" onclick="if(event.target===this)this.remove()">
      <div id="trial-eval-modal" class="bg-white rounded-xl shadow-xl w-full max-w-lg max-h-[90vh] flex flex-col" onclick="event.stopPropagation()">
        <div class="flex items-center justify-between px-5 pt-4 pb-2 flex-shrink-0">
          <h3 class="text-base font-semibold text-gray-800">试评估</h3>
          <button onclick="document.getElementById('trial-eval-overlay').remove()"
            class="text-gray-400 hover:text-gray-600 text-lg leading-none">&times;</button>
        </div>
        <div class="overflow-y-auto px-5 pb-5 flex-1 min-h-0">
          <div id="trial-eval-form-area">
            <p class="text-xs text-gray-500 mb-4">上传一份带标签的 CSV 文件，平台将临时加载模型进行预测并对比训练指标。</p>
            <form id="form-trial-eval" onsubmit="runTrialEvaluate(event,'${versionId}')">
              <input type="file" name="file" accept=".csv" required
                class="w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-medium file:bg-brand-50 file:text-brand-700 hover:file:bg-brand-100 mb-4">
              <p class="text-xs text-gray-400 mb-4">CSV 须包含特征列和目标列（标签），特征列名需与模型特征定义一致。</p>
              <div class="flex justify-end gap-2">
                <button type="submit" id="trial-eval-submit"
                  class="px-4 py-2 bg-brand-600 text-white text-sm rounded-lg hover:bg-brand-700 font-medium">开始评估</button>
              </div>
            </form>
          </div>
          <div id="trial-eval-result" class="hidden"></div>
        </div>
      </div>
    </div>
  `;
  document.body.insertAdjacentHTML('beforeend', html);
}

async function runTrialEvaluate(e, versionId) {
  e.preventDefault();
  const btn = document.getElementById('trial-eval-submit');
  const resultDiv = document.getElementById('trial-eval-result');
  const fd = new FormData(e.target);

  btn.disabled = true;
  btn.textContent = '评估中...';
  resultDiv.classList.add('hidden');

  try {
    const res = await fetch(
      API + `/models/${currentModelId}/versions/${versionId}/trial-evaluate`,
      { method: 'POST', body: fd }
    );
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || JSON.stringify(err));
    }
    const data = await res.json();
    // Collapse form, widen modal for two-column layout
    const formArea = document.getElementById('trial-eval-form-area');
    if (formArea) formArea.classList.add('hidden');
    const modal = document.getElementById('trial-eval-modal');
    if (modal && data.diagnosis) {
      modal.classList.remove('max-w-lg');
      modal.classList.add('max-w-4xl');
    }
    renderTrialResult(resultDiv, data, versionId);
    resultDiv.classList.remove('hidden');
  } catch (err) {
    showToast(err.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = '开始评估';
  }
}

var _lastTrialData = null;  // stash for forkAndAdapt to pick up

function renderTrialResult(container, data, versionId) {
  _lastTrialData = data;
  const verdictConfig = {
    compatible: { label: '兼容', color: 'green', icon: '&#10003;' },
    moderate_degradation: { label: '轻度退化', color: 'yellow', icon: '&#9888;' },
    severe_degradation: { label: '严重退化', color: 'red', icon: '&#10007;' },
  };
  const vc = verdictConfig[data.verdict] || verdictConfig.compatible;
  const colorMap = {
    green: { bg: 'bg-green-50', border: 'border-green-200', text: 'text-green-700' },
    yellow: { bg: 'bg-yellow-50', border: 'border-yellow-200', text: 'text-yellow-700' },
    red: { bg: 'bg-red-50', border: 'border-red-200', text: 'text-red-700' },
  };
  const cm = colorMap[vc.color];

  // ── Metrics comparison table ──
  const rows = data.comparison.map(c => {
    const trainVal = c.training_value != null ? c.training_value.toFixed(4) : '-';
    const trialVal = c.trial_value.toFixed(4);
    let deltaHtml = '-';
    if (c.delta_percent != null) {
      const sign = c.delta_percent > 0 ? '+' : '';
      const dc = c.delta_percent > 20 ? 'text-red-600' : c.delta_percent > 0 ? 'text-yellow-600' : 'text-green-600';
      deltaHtml = `<span class="${dc} font-medium">${sign}${c.delta_percent.toFixed(1)}%</span>`;
    }
    return `<tr class="border-t border-gray-100">
      <td class="py-1.5 pr-3 text-xs text-gray-600 font-medium">${c.name}</td>
      <td class="py-1.5 pr-3 text-xs text-gray-500 text-right font-mono">${trainVal}</td>
      <td class="py-1.5 pr-3 text-xs text-gray-900 text-right font-mono">${trialVal}</td>
      <td class="py-1.5 text-xs text-right">${deltaHtml}</td>
    </tr>`;
  }).join('');

  // ── Action buttons ──
  let actionHtml = '';
  if (data.verdict === 'compatible') {
    actionHtml = `
      <div class="flex items-center justify-between mt-3 pt-3 border-t border-green-200">
        <span class="text-xs text-gray-500">模型兼容，可直接部署</span>
        <button onclick="document.getElementById('trial-eval-overlay').remove();switchSubTab('deploy')"
          class="px-4 py-1.5 bg-green-600 text-white text-xs rounded-lg hover:bg-green-700 font-medium">
          去部署
        </button>
      </div>`;
  } else {
    actionHtml = `
      <div class="mt-3 pt-3 border-t ${cm.border}">
        <div class="flex items-center gap-2">
          <input id="fork-org-input" type="text" placeholder="您的组织名称" value=""
            class="flex-1 px-3 py-1.5 text-xs border border-gray-300 rounded-lg focus:outline-none focus:border-brand-500">
          <button onclick="forkAndAdapt('${versionId}')" id="fork-adapt-btn"
            class="px-4 py-1.5 bg-brand-600 text-white text-xs rounded-lg hover:bg-brand-700 font-medium whitespace-nowrap">
            Fork 并适配
          </button>
        </div>
      </div>`;
  }

  // ── Left column: verdict + metrics + action ──
  const leftCol = `
    <div>
      <div class="${cm.bg} ${cm.border} border rounded-lg p-4">
        <div class="flex items-center justify-between mb-3">
          <span class="text-sm font-medium ${cm.text}">${vc.icon} ${vc.label}</span>
          <span class="text-xs text-gray-500">${data.sample_count} 条 · ${data.features_matched}/${data.features_total} 特征</span>
        </div>
        <table class="w-full">
          <thead>
            <tr class="text-xs text-gray-400">
              <th class="text-left pr-3 pb-1.5 font-medium">指标</th>
              <th class="text-right pr-3 pb-1.5 font-medium">训练值</th>
              <th class="text-right pr-3 pb-1.5 font-medium">试评估</th>
              <th class="text-right pb-1.5 font-medium">变化</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
        ${actionHtml}
      </div>
    </div>`;

  // ── No diagnosis → single column ──
  if (!data.diagnosis) {
    container.innerHTML = leftCol;
    return;
  }

  // ── Right column: diagnosis ──
  const d = data.diagnosis;

  // Recommendations
  const recHtml = d.recommendations.map(r => {
    const icons = { critical: '&#10007;', warning: '&#9888;', info: '&#8505;' };
    const colors = {
      critical: 'text-red-600 bg-red-50 border-red-200',
      warning: 'text-yellow-700 bg-yellow-50 border-yellow-200',
      info: 'text-blue-600 bg-blue-50 border-blue-200',
    };
    const c = colors[r.severity] || colors.info;
    return `<div class="flex gap-2 p-2 rounded border ${c}">
      <span class="text-sm flex-shrink-0">${icons[r.severity] || ''}</span>
      <span class="text-xs leading-relaxed">${r.message}</span>
    </div>`;
  }).join('');

  // Feature importance bars
  const top = d.feature_importance.slice(0, 6);
  const maxVal = top[0]?.importance || 1;
  const impHtml = top.map(f => {
    const pct = Math.min(100, (f.importance / maxVal) * 100);
    return `<div class="flex items-center gap-2 text-xs">
      <span class="w-24 text-gray-600 truncate text-right flex-shrink-0">${f.name}</span>
      <div class="flex-1 bg-gray-200 rounded-full h-1.5"><div class="bg-brand-500 h-1.5 rounded-full" style="width:${pct.toFixed(0)}%"></div></div>
      <span class="w-10 text-gray-400 font-mono text-right flex-shrink-0">${f.importance.toFixed(0)}</span>
    </div>`;
  }).join('');

  // Drift table
  const drifted = d.drift_report.filter(f => f.psi_severity !== 'none');
  const driftHtml = drifted.map(f => {
    const sc = f.psi_severity === 'significant' ? 'text-red-600' : 'text-yellow-600';
    return `<tr class="border-t border-gray-100">
      <td class="py-1 text-xs text-gray-600">${f.name}</td>
      <td class="py-1 text-xs text-gray-400 text-right">${f.ref_mean}±${f.ref_std}</td>
      <td class="py-1 text-xs text-gray-400 text-right">${f.tgt_mean}±${f.tgt_std}</td>
      <td class="py-1 text-xs ${sc} text-right font-medium">${f.psi.toFixed(2)}</td>
    </tr>`;
  }).join('');

  const rightCol = `
    <div class="space-y-3">
      ${recHtml ? `<div class="space-y-1.5">${recHtml}</div>` : ''}
      ${impHtml ? `
        <div class="bg-gray-50 rounded-lg p-3">
          <h4 class="text-xs font-semibold text-gray-700 mb-2">特征重要性 (SHAP)</h4>
          <div class="space-y-1.5">${impHtml}</div>
        </div>` : ''}
      ${driftHtml ? `
        <div class="bg-gray-50 rounded-lg p-3">
          <h4 class="text-xs font-semibold text-gray-700 mb-2">分布漂移 (${drifted.length} 项偏移)</h4>
          <table class="w-full">
            <thead><tr class="text-xs text-gray-400">
              <th class="text-left pb-1 font-medium">特征</th>
              <th class="text-right pb-1 font-medium">训练</th>
              <th class="text-right pb-1 font-medium">您的</th>
              <th class="text-right pb-1 font-medium">PSI</th>
            </tr></thead>
            <tbody>${driftHtml}</tbody>
          </table>
        </div>` : ''}
    </div>`;

  container.innerHTML = `<div class="grid grid-cols-2 gap-4">${leftCol}${rightCol}</div>`;
}

async function forkAndAdapt(versionId) {
  const orgInput = document.getElementById('fork-org-input');
  const org = orgInput.value.trim();
  if (!org) {
    orgInput.focus();
    showToast('请输入您的组织名称', 'error');
    return;
  }

  const btn = document.getElementById('fork-adapt-btn');
  btn.disabled = true;
  btn.textContent = '创建中...';

  try {
    const srcName = currentModelData.name;
    const newName = `${srcName}-${org}适配`;

    const result = await api(`/models/${currentModelId}/fork`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        source_version_id: versionId,
        new_name: newName,
        new_owner_org: org,
        description: `从 ${srcName} Fork，用于 ${org} 本地适配`,
      }),
    });

    // Stash diagnosis for guidance banner on the forked version
    if (_lastTrialData && _lastTrialData.diagnosis) {
      pendingAdaptGuide = _lastTrialData;
    }

    // Close overlay and navigate to the new model's version tab
    document.getElementById('trial-eval-overlay').remove();
    showToast(`已创建 "${newName}"，请在版本中修改数据和参数后训练`);

    // Load new model detail and jump directly to versions tab with output stage
    const [model, versions] = await Promise.all([
      api('/models/' + result.id),
      api('/models/' + result.id + '/versions'),
    ]);
    currentModelId = result.id;
    currentModelData = model;
    currentModelVersions = versions;
    document.getElementById('detail-breadcrumb').textContent = model.name;
    renderDetailHeader(model);
    switchPage('model-detail');

    // Expand the forked version and show output stage with guidance banner
    if (versions.length) {
      expandedVersionId = versions[0].id;
      activePipelineStage = 'output';
      artifactTabCache = {};
    }
    switchSubTab('versions');
  } catch (err) {
    showToast(err.message, 'error');
    btn.disabled = false;
    btn.textContent = 'Fork 并适配';
  }
}

// ── Retrain ──

let retrainRunId = null;
let retrainPollTimer = null;

async function showRetrain(versionId) {
  const v = currentModelVersions.find(x => x.id === versionId);
  if (!v) return;

  // Create overlay immediately with loading state
  const html = `
    <div class="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4"
         id="retrain-overlay" onclick="if(event.target===this){stopRetrainPolling();this.remove()}">
      <div class="bg-white rounded-xl shadow-xl w-full max-w-xl max-h-[90vh] flex flex-col" onclick="event.stopPropagation()">
        <div class="flex items-center justify-between px-5 pt-4 pb-2 flex-shrink-0">
          <h3 class="text-base font-semibold text-gray-800">重新训练</h3>
          <button onclick="stopRetrainPolling();document.getElementById('retrain-overlay').remove()"
            class="text-gray-400 hover:text-gray-600 text-lg leading-none">&times;</button>
        </div>
        <div class="overflow-y-auto px-5 pb-5 flex-1 min-h-0">
          <div id="retrain-config" class="text-sm text-gray-500">加载配置中...</div>
          <div id="retrain-progress" class="hidden"></div>
        </div>
      </div>
    </div>
  `;
  document.body.insertAdjacentHTML('beforeend', html);

  // Load pipeline and all artifact categories in parallel
  try {
    const [pipeline, datasets, codeFiles, featFiles, paramFiles] = await Promise.all([
      api('/models/' + currentModelId + '/pipeline'),
      api('/models/' + currentModelId + '/versions/' + versionId + '/artifacts/datasets'),
      api('/models/' + currentModelId + '/versions/' + versionId + '/artifacts/code'),
      api('/models/' + currentModelId + '/versions/' + versionId + '/artifacts/features'),
      api('/models/' + currentModelId + '/versions/' + versionId + '/artifacts/params'),
    ]);

    if (!pipeline.exists) {
      document.getElementById('retrain-config').innerHTML =
        '<div class="text-center py-6">' +
          '<div class="text-red-500 mb-2">未定义训练流水线</div>' +
          '<div class="text-xs text-gray-400">请先在「流水线」标签页配置 pipeline.yaml</div>' +
        '</div>';
      return;
    }

    const p = pipeline.data || {};
    const dp = p.data_prep || {};
    const tr = p.training || {};
    var hasWeights = !!v.file_path;

    // Detect file name mismatches between pipeline config and actual files
    var dsFileNames = (datasets || []).map(function(f) { return f.name; }).filter(function(n) { return n.endsWith('.csv'); });
    var featFileNames = (featFiles || []).map(function(f) { return f.name; }).filter(function(n) { return n.endsWith('.yaml') || n.endsWith('.yml'); });
    var paramFileNames = (paramFiles || []).map(function(f) { return f.name; }).filter(function(n) { return n.endsWith('.yaml') || n.endsWith('.yml'); });
    var hasScript = (codeFiles || []).some(function(f) { return f.name === tr.script; });

    var pipelineDs = dp.dataset || '';
    var pipelineFeat = dp.feature_config || '';
    var pipelineParams = tr.params || '';

    var dsMismatch = pipelineDs && dsFileNames.length > 0 && dsFileNames.indexOf(pipelineDs) === -1;
    var featMismatch = pipelineFeat && featFileNames.length > 0 && featFileNames.indexOf(pipelineFeat) === -1;
    var paramMismatch = pipelineParams && paramFileNames.length > 0 && paramFileNames.indexOf(pipelineParams) === -1;
    var hasMismatch = dsMismatch || featMismatch || paramMismatch;

    // Helper: build <select> for file override
    function fileSelect(id, pipelineName, fileList, mismatch) {
      if (!mismatch && fileList.length <= 1) {
        return '<span class="font-medium">' + (pipelineName || '无') + '</span>';
      }
      var opts = '';
      if (!mismatch) {
        opts += '<option value="">' + pipelineName + '</option>';
      }
      for (var i = 0; i < fileList.length; i++) {
        var selected = (mismatch && fileList.length === 1) ? ' selected' : '';
        opts += '<option value="' + fileList[i] + '"' + selected + '>' + fileList[i] + '</option>';
      }
      if (mismatch && fileList.length > 1) {
        opts = '<option value="">-- 请选择 --</option>' + opts;
      }
      return '<select id="' + id + '" class="text-xs border rounded px-1 py-0.5 font-medium ' +
        (mismatch ? 'border-amber-400 bg-amber-50' : '') + '">' + opts + '</select>';
    }

    var configHtml = '<div class="space-y-3">';

    // Mismatch warning
    if (hasMismatch) {
      configHtml +=
        '<div class="bg-amber-50 border border-amber-200 rounded-lg p-2 text-xs text-amber-700">' +
          '流水线配置的文件名与版本中实际文件不匹配，请确认以下文件映射：' +
        '</div>';
    }

    configHtml +=
      '<div class="bg-gray-50 rounded-lg p-3">' +
        '<div class="text-xs font-semibold text-gray-600 mb-2">训练配置</div>' +
        '<div class="grid grid-cols-2 gap-x-4 gap-y-2 text-xs items-center">' +
          '<div><span class="text-gray-400">基础版本:</span> <span class="font-medium">v' + v.version + '</span></div>' +
          '<div><span class="text-gray-400">训练脚本:</span> <span class="font-medium ' + (hasScript ? '' : 'text-red-500') + '">' + (tr.script || '未指定') + '</span></div>' +
          '<div><span class="text-gray-400">数据集' + (dsMismatch ? ' ⚠' : '') + ':</span> ' + fileSelect('retrain-ds', pipelineDs, dsFileNames, dsMismatch) + '</div>' +
          '<div><span class="text-gray-400">特征' + (featMismatch ? ' ⚠' : '') + ':</span> ' + fileSelect('retrain-feat', pipelineFeat, featFileNames, featMismatch) + '</div>' +
          '<div><span class="text-gray-400">超参数' + (paramMismatch ? ' ⚠' : '') + ':</span> ' + fileSelect('retrain-params', pipelineParams, paramFileNames, paramMismatch) + '</div>' +
        '</div>' +
      '</div>';

    if (hasWeights) {
      configHtml +=
        '<label class="flex items-center gap-2 px-1 cursor-pointer">' +
          '<input type="checkbox" id="retrain-warm-start" checked ' +
            'class="w-4 h-4 rounded border-gray-300 text-green-600 focus:ring-green-500">' +
          '<span class="text-xs text-gray-700">热启动（迁移学习）：在当前模型权重基础上继续训练</span>' +
        '</label>';
    }
    configHtml +=
      '<div class="flex justify-end gap-2 pt-1">' +
        '<button type="button" onclick="stopRetrainPolling();document.getElementById(\'retrain-overlay\').remove()" ' +
          'class="px-4 py-2 text-sm text-gray-600 hover:bg-gray-100 rounded-lg">取消</button>' +
        '<button id="retrain-submit" onclick="runRetrain(\'' + versionId + '\')" ' +
          'class="px-4 py-2 bg-green-600 text-white text-sm rounded-lg hover:bg-green-700 font-medium' +
          (hasScript ? '' : ' opacity-50 cursor-not-allowed') + '"' +
          (hasScript ? '' : ' disabled') + '>开始训练</button>' +
      '</div>' +
    '</div>';
    document.getElementById('retrain-config').innerHTML = configHtml;
  } catch (err) {
    document.getElementById('retrain-config').innerHTML =
      '<div class="text-center py-6 text-red-500 text-sm">' + escapeHtml(err.message) + '</div>';
  }
}

async function runRetrain(versionId) {
  const v = currentModelVersions.find(x => x.id === versionId);
  if (!v) return;

  const btn = document.getElementById('retrain-submit');
  btn.disabled = true;
  btn.textContent = '启动中...';

  try {
    const body = { base_version: 'v' + v.version };
    var overrides = {};
    // Collect file overrides from selects
    var dsSel = document.getElementById('retrain-ds');
    if (dsSel && dsSel.value) overrides.dataset = dsSel.value;
    var featSel = document.getElementById('retrain-feat');
    if (featSel && featSel.value) overrides.feature_config = featSel.value;
    var paramSel = document.getElementById('retrain-params');
    if (paramSel && paramSel.value) overrides.params = paramSel.value;
    // Warm-start
    var wsCheckbox = document.getElementById('retrain-warm-start');
    if (wsCheckbox && wsCheckbox.checked && v.file_path) {
      var weightsFile = v.file_path.split('/').pop();
      overrides.warm_start = weightsFile;
    }
    if (Object.keys(overrides).length) body.overrides = overrides;

    const run = await api('/models/' + currentModelId + '/pipeline/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });

    // Switch to progress view
    document.getElementById('retrain-config').classList.add('hidden');
    const progress = document.getElementById('retrain-progress');
    progress.classList.remove('hidden');
    renderRetrainProgress(progress, run);

    retrainRunId = run.id;
    startRetrainPolling();
  } catch (err) {
    showToast(err.message, 'error');
    btn.disabled = false;
    btn.textContent = '开始训练';
  }
}

function startRetrainPolling() {
  stopRetrainPolling();
  retrainPollTimer = setInterval(pollRetrainStatus, 2000);
}

function stopRetrainPolling() {
  if (retrainPollTimer) { clearInterval(retrainPollTimer); retrainPollTimer = null; }
}

async function pollRetrainStatus() {
  if (!retrainRunId || !currentModelId) { stopRetrainPolling(); return; }
  try {
    const run = await api('/models/' + currentModelId + '/pipeline/runs/' + retrainRunId);
    const progress = document.getElementById('retrain-progress');
    if (!progress) { stopRetrainPolling(); return; }
    renderRetrainProgress(progress, run);
    if (run.status === 'success' || run.status === 'failed') {
      stopRetrainPolling();
      retrainRunId = null;
      if (run.status === 'success') {
        currentModelVersions = await api('/models/' + currentModelId + '/versions');
      }
    }
  } catch (e) {
    stopRetrainPolling();
  }
}

function renderRetrainProgress(container, run) {
  const statusColors = {
    pending: 'bg-yellow-100 text-yellow-700 border-yellow-300',
    running: 'bg-blue-100 text-blue-700 border-blue-300',
    success: 'bg-green-100 text-green-700 border-green-300',
    failed: 'bg-red-100 text-red-700 border-red-300',
  };
  const statusLabels = { pending: '准备中', running: '训练中', success: '训练完成', failed: '训练失败' };
  const sc = statusColors[run.status] || statusColors.pending;
  const sl = statusLabels[run.status] || run.status;

  var logHtml = run.log
    ? '<pre class="mt-3 p-3 bg-gray-900 text-green-400 text-[11px] font-mono rounded-lg max-h-48 overflow-y-auto whitespace-pre-wrap">' + escapeHtml(run.log) + '</pre>'
    : '<div class="mt-3 text-xs text-gray-400 italic">等待日志输出...</div>';

  var metricsHtml = '';
  if (run.metrics) {
    var cards = Object.entries(run.metrics)
      .filter(function(e) { return typeof e[1] === 'number'; })
      .map(function(e) {
        return '<div class="text-center p-2 bg-white rounded border">' +
          '<div class="text-[10px] text-gray-400">' + e[0] + '</div>' +
          '<div class="text-sm font-semibold text-gray-700">' + e[1].toFixed(4) + '</div></div>';
      }).join('');
    metricsHtml = '<div class="mt-3 grid grid-cols-3 gap-2">' + cards + '</div>';
  }

  var actionHtml = '';
  if (run.status === 'success' && run.result_version_id) {
    actionHtml =
      '<div class="mt-3 flex justify-end">' +
        '<button onclick="viewNewVersion(\'' + run.result_version_id + '\')" ' +
          'class="px-4 py-2 bg-green-600 text-white text-sm rounded-lg hover:bg-green-700 font-medium">' +
          '查看新版本 v' + (run.result_version || '') +
        '</button>' +
      '</div>';
  } else if (run.status === 'failed') {
    actionHtml = '<div class="mt-3">';
    if (run.error) {
      actionHtml += '<div class="text-xs text-red-600 bg-red-50 rounded p-2 mb-2">' + escapeHtml(run.error) + '</div>';
    }
    actionHtml +=
        '<div class="flex justify-end">' +
          '<button onclick="stopRetrainPolling();document.getElementById(\'retrain-overlay\').remove()" ' +
            'class="px-4 py-2 text-sm text-gray-600 hover:bg-gray-100 rounded-lg">关闭</button>' +
        '</div>' +
      '</div>';
  }

  container.innerHTML =
    '<div class="border rounded-lg p-4 ' + sc + '">' +
      '<div class="flex items-center justify-between">' +
        '<div class="flex items-center gap-2">' +
          '<span class="text-sm font-medium">' + sl + '</span>' +
          (run.status === 'running' ? '<span class="inline-block w-2 h-2 bg-blue-500 rounded-full animate-pulse"></span>' : '') +
        '</div>' +
        '<div class="text-[10px] text-gray-500">' +
          (run.base_version || '') + ' &rarr; v' + (run.target_version || '...') +
          (run.finished_at ? ' | ' + formatTime(run.finished_at) : '') +
        '</div>' +
      '</div>' +
      metricsHtml +
      logHtml +
      actionHtml +
    '</div>';

  // Auto-scroll log
  var logEl = container.querySelector('pre');
  if (logEl) logEl.scrollTop = logEl.scrollHeight;
}

function viewNewVersion(versionId) {
  stopRetrainPolling();
  var overlay = document.getElementById('retrain-overlay');
  if (overlay) overlay.remove();
  expandedVersionId = versionId;
  activePipelineStage = 'output';
  artifactTabCache = {};
  renderVersionsTab();
}

// ── Adaptation Guide ──

function dismissAdaptGuide() {
  pendingAdaptGuide = null;
  if (expandedVersionId && activePipelineStage === 'output') {
    invalidateArtifactCache(expandedVersionId);
    loadPipelineStage(expandedVersionId, 'output');
  }
}

// ── Init ──

checkHealth();
setInterval(checkHealth, 10000);
switchPage('models');
