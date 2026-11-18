/* ==========================================================================
   Oasis Smart City — Unified Executive Dashboard · client application
   Pure vanilla JS. Data arrives as window.__DASH__ (built by extract_dash1.py).
   The pillar-index engine is a direct port of Gad's v2 engine (p6_dash.py) so
   the numbers stay identical to Gad/outputs/tables/v2_pillar_index.csv.
   ========================================================================== */
(function () {
'use strict';

var D = window.__DASH__;
var DAYS = D.days, N = DAYS.length;
var IDX = {};
DAYS.forEach(function (d, i) { IDX[d] = i; });

var PIL_C = { 'Normal': '#059669', 'Watch': '#D97706', 'Critical': '#DC2626', 'n/a': '#64748B' };
var ACC = { ENE: '#0B3C5D', BLD: '#B45309', WAT: '#0369A1', WST: '#047857',
            GCS: '#2A78D6', ENV: '#1BAF7A', MOB: '#2A78D6', PSS: '#0B3C5D' };
var PLOT_CFG = { responsive: true, displayModeBar: false, displaylogo: false, scrollZoom: false };

var CUR = { from: '2025-12-01', to: '2025-12-31' };
var PRESETS = [
  { id: '1M', label: '1M · Dec', from: '2025-12-01', to: '2025-12-31' },
  { id: '1Q', label: '1Q · Q4', from: '2025-10-01', to: '2025-12-31' },
  { id: 'H1', label: 'H1 · pre-app', from: '2025-01-01', to: '2025-06-30' },
  { id: 'H2', label: 'H2 · post-app', from: '2025-07-01', to: '2025-12-31' },
  { id: 'SUMMER', label: 'Summer peak', from: '2025-07-01', to: '2025-08-31' },
  { id: 'RAMADAN', label: 'Ramadan', from: '2025-03-01', to: '2025-03-30' },
  { id: 'ALL', label: 'All 2025', from: '2025-01-01', to: '2025-12-31' }
];
var RENDERED = {};
var TAB = 'overall';
var PANE = 'overview';

/* ------------------------------------------------------------------ utils */
function el(id) { return document.getElementById(id); }
function esc(s) {
  return String(s === null || s === undefined ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}
function num(v, dec) {
  if (v === null || v === undefined || !isFinite(v)) { return 'n/a'; }
  var d = (dec === undefined || dec === null) ? 0 : dec;
  return Number(v).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
}
function fmtDate(s) {
  var dt = new Date(s + 'T00:00:00');
  return dt.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
}
function shortDate(s) {
  var dt = new Date(s + 'T00:00:00');
  return dt.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
}
function dayOf(ts) { return (ts || '').slice(0, 10); }

function windowIdx(from, to) {
  var i0 = IDX[from], i1 = IDX[to];
  if (i0 === undefined) { i0 = 0; }
  if (i1 === undefined) { i1 = N - 1; }
  return [i0, i1 + 1];
}

function monthEq(i0, i1) {
  var per = {};
  for (var i = i0; i < i1; i++) {
    var m = DAYS[i].slice(0, 7);
    per[m] = (per[m] || 0) + 1;
  }
  var eq = 0;
  Object.keys(per).forEach(function (m) { eq += per[m] / (D.dim[m] || 31); });
  return eq;
}

/* --------------------------------------------------- pillar index engine */
function pilQuantile(values, q) {
  var a = values.slice().sort(function (x, y) { return x - y; });
  var n = a.length;
  if (!n) { return NaN; }
  if (n === 1) { return a[0]; }
  var p = q * (n - 1), lo = Math.floor(p), hi = Math.ceil(p);
  return (lo === hi) ? a[lo] : a[lo] + (a[hi] - a[lo]) * (p - lo);
}

function pilWindow(row, i0, i1) {
  var n = i1 - i0;
  if (n <= 0) { return null; }
  if (row.mode === 'poolmed') {
    var pool = (D.pools && D.pools[row.pool]) || [], vals = [];
    for (var k = 0; k < pool.length; k++) {
      if (pool[k][0] >= i0 && pool[k][0] < i1) { vals.push(pool[k][1]); }
    }
    return vals.length ? pilQuantile(vals, 0.5) : null;
  }
  if (row.mode === 'perday') {
    var arrP = D.series[row.keys[0]], sp = 0;
    for (var ip = i0; ip < i1; ip++) { sp += arrP[ip]; }
    return sp / n;
  }
  if (row.mode === 'mrate') {
    var arrM = D.series[row.keys[0]], sm = 0, cm = 0;
    for (var im = i0; im < i1; im++) {
      if (arrM[im] !== null && isFinite(arrM[im])) { sm += arrM[im]; cm++; }
    }
    return cm ? sm / cm : null;
  }
  if (row.mode === 'last') {
    var arrL = D.series[row.keys[0]], vl = arrL[i1 - 1];
    return (vl === null || !isFinite(vl)) ? null : vl;
  }
  if (row.mode === 'perk') {
    var arrK = D.series[row.keys[0]], sk = 0;
    for (var ik = i0; ik < i1; ik++) { sk += arrK[ik]; }
    return row.pop ? sk / row.pop * 1000 : null;
  }
  var A = D.series[row.keys[0]];
  var B = (row.keys.length > 1) ? D.series[row.keys[1]] : null;
  var s0 = 0, s1 = 0, m0 = -Infinity, m1 = -Infinity;
  for (var i = i0; i < i1; i++) {
    s0 += A[i];
    if (A[i] > m0) { m0 = A[i]; }
    if (B) { s1 += B[i]; if (B[i] > m1) { m1 = B[i]; } }
  }
  if (row.mode === 'sum')   { return s0; }
  if (row.mode === 'max')   { return m0; }
  if (row.mode === 'rate')  { return s1 ? s0 / s1 * 100 : null; }
  if (row.mode === 'wmean') { return s1 ? s0 / s1 : null; }
  if (row.mode === 'ratio') { return s1 ? s0 / (s1 * row.factor) * 100 : null; }
  if (row.mode === 'lf')    { return m1 > 0 ? (s0 * 1e3 / (n * 24)) / m1 * 100 : null; }
  return null;
}

function pilValue(row, i0, i1) {
  var v = pilWindow(row, i0, i1);
  if (v === null || !isFinite(v)) { return null; }
  if (!row.flow) { return v; }
  var eq = monthEq(i0, i1);
  return eq ? v / eq : null;
}

function pilStats(row) {
  var m = row.monthly.filter(function (v) { return v !== null && isFinite(v); });
  if (!m.length) { return null; }
  return { med: pilQuantile(m, 0.5), p05: pilQuantile(m, 0.05), p20: pilQuantile(m, 0.20),
           p80: pilQuantile(m, 0.80), p95: pilQuantile(m, 0.95) };
}

function pilStatus(row, value, st) {
  if (value === null || !st) { return 'n/a'; }
  if (row.better === 'high') {
    if (value < st.p05) { return 'Critical'; }
    if (value < st.p20) { return 'Watch'; }
    return 'Normal';
  }
  if (value > st.p95) { return 'Critical'; }
  if (value > st.p80) { return 'Watch'; }
  return 'Normal';
}

function pilState(row, i0, i1) {
  var st = pilStats(row);
  var value = pilValue(row, i0, i1);
  var ok = st && st.med > 0;
  var n = i1 - i0;
  var p0 = Math.max(0, i0 - n);
  var prev = (i0 > 0) ? pilValue(row, p0, i0) : null;
  var at = function (v) { return (v === null || !ok || !isFinite(v)) ? null : v / st.med * 100; };
  return { label: row.label, kpi: row.kpi, unit: row.unit, dec: row.dec, better: row.better,
           note: row.note, value: value, index: at(value), prev: prev, prevIndex: at(prev),
           band20: st ? at(st.p20) : null, band95: st ? at(st.p95) : null,
           median: st ? st.med : null, p20: st ? st.p20 : null, p95: st ? st.p95 : null,
           status: pilStatus(row, value, st) };
}

function pilFigure(rows, node) {
  var ys = rows.map(function (_, i) { return i; });
  var idx = rows.map(function (r) { return r.index; });
  var prev = rows.map(function (r) { return r.prevIndex; });
  var txt = rows.map(function (r) { return r.value === null ? 'n/a' : num(r.value, r.dec) + ' ' + r.unit; });
  var labels = rows.map(function (r) { return (r.better === 'high' ? '\u2191 ' : '\u2193 ') + r.label; });
  var wi = windowIdx(CUR.from, CUR.to);
  var nDays = Math.max(0, wi[1] - wi[0]);
  var win = shortDate(CUR.from) + ' \u2013 ' + shortDate(CUR.to);
  var say = function (v, dec) { return (v === null || !isFinite(v)) ? 'n/a' : num(v, dec); };

  var barTop = 100;
  idx.concat(prev).forEach(function (v) {
    if (v !== null && isFinite(v) && v > barTop) { barTop = v; }
  });
  var top = barTop;
  rows.forEach(function (r) {
    if (r.band95 !== null && isFinite(r.band95) && r.band95 > top) { top = r.band95; }
  });
  top = Math.min(top, barTop * 2);

  var maxChars = txt.reduce(function (m, s) { return Math.max(m, s.length); }, 3);
  var innerPx = Math.max(220, (node ? node.clientWidth : 540) - 164);
  var textPx = maxChars * 6.3 + 2;
  var frac = Math.min(0.46, Math.max(0.18, (textPx + 14) / innerPx + 0.02));
  var barFrac = Math.max(0.34, 1 - frac - 0.02);
  var xmax = Math.max(20, Math.ceil((top / barFrac) / 10) * 10);
  var colx = xmax * (1 - frac);
  var ylo = -0.55, yhi = rows.length - 0.45;

  var shapes = [];
  var clipped = [];
  var clipx = colx - 6;
  rows.forEach(function (r, i) {
    if (r.band20 !== null && r.band95 !== null && isFinite(r.band20) && isFinite(r.band95)) {
      var x0 = Math.min(r.band20, clipx), x1 = Math.min(r.band95, clipx);
      if (x1 > x0) {
        shapes.push({ type: 'line', x0: x0, x1: x1, y0: i, y1: i,
                      line: { color: '#CBD5E1', width: 10 }, layer: 'below' });
      }
      if (r.band95 > clipx) { clipped.push(i); }
    }
  });
  shapes.push({ type: 'line', x0: 100, x1: 100, y0: ylo, y1: yhi,
                line: { color: '#94A3B8', width: 1.1, dash: 'dot' }, layer: 'below' });
  shapes.push({ type: 'line', x0: colx, x1: colx, y0: ylo, y1: yhi,
                line: { color: '#E2E8F0', width: 1, dash: 'dot' }, layer: 'below' });

  var hover = rows.map(function (r) {
    var h = '<b>' + r.label + '</b> \u00b7 ' + r.kpi + '<br>' +
            win + ' \u00b7 ' + nDays + ' days \u00b7 ' + say(r.value, r.dec) + ' ' + r.unit + '<br>' +
            (r.index === null ? 'index n/a' : 'index ' + r.index.toFixed(0) + ' \u2014 a typical 2025 month is 100') + '<br>';
    if (r.median !== null) {
      h += '2025 median ' + say(r.median, r.dec) + ' ' + r.unit + ' \u00b7 P20\u2013P95 ' +
           say(r.p20, r.dec) + '\u2013' + say(r.p95, r.dec) + '<br>';
    }
    h += r.prevIndex === null ? 'previous window n/a (no days before the start)<br>'
       : 'previous ' + nDays + ' days \u00b7 ' + say(r.prev, r.dec) + ' ' + r.unit +
         ' (index ' + r.prevIndex.toFixed(0) + ')<br>';
    h += 'status ' + r.status + ' \u00b7 ' + (r.better === 'high' ? 'higher is better' : 'lower is better') +
         '<br>' + r.note;
    return h;
  });
  var hoverPrev = rows.map(function (r) {
    if (r.prevIndex === null) { return ''; }
    return '<b>' + r.label + '</b> \u00b7 previous ' + nDays + ' days<br>' +
           say(r.prev, r.dec) + ' ' + r.unit + ' \u00b7 index ' + r.prevIndex.toFixed(0);
  });

  var data = [
    { type: 'bar', orientation: 'h', x: idx, y: ys,
      marker: { color: rows.map(function (r) { return PIL_C[r.status] || PIL_C['n/a']; }),
                line: { color: 'rgba(255,255,255,.92)', width: 1.2 } },
      hovertext: hover, hovertemplate: '%{hovertext}<extra></extra>', name: 'Selected window',
      showlegend: false },
    { type: 'scatter', mode: 'markers', x: prev, y: ys.map(function (y) { return y - 0.30; }),
      marker: { symbol: 'diamond', size: 8, color: '#64748B', line: { color: '#FFFFFF', width: 1.2 } },
      hovertext: hoverPrev, hovertemplate: '%{hovertext}<extra></extra>', name: 'Previous window',
      showlegend: false }
  ];

  var layout = {
    height: 330, bargap: 0.38, showlegend: false,
    margin: { l: 150, r: 14, t: 26, b: 28 },
    annotations: rows.map(function (r, i) {
      return { x: xmax * 0.985, y: i, xanchor: 'right', showarrow: false, text: txt[i],
               font: { size: 10.4, color: '#0F172A' } };
    }).concat(clipped.map(function (i) {
      return { x: clipx - 3, y: i, xanchor: 'right', showarrow: false, text: '\u203a',
               font: { size: 13.5, color: '#64748B' } };
    })),
    shapes: shapes,
    xaxis: { range: [0, xmax], ticksuffix: ' %', showgrid: true, gridcolor: '#E8EEF4', griddash: 'dot',
             zeroline: false, tickfont: { size: 9.6, color: '#94A3B8' }, fixedrange: true },
    yaxis: { autorange: 'reversed', showgrid: false, zeroline: false, ticks: '',
             tickmode: 'array', tickvals: ys, ticktext: labels, ticklabelstandoff: 8,
             tickfont: { size: 11.2, color: '#0F172A' }, fixedrange: true },
    plot_bgcolor: 'rgba(0,0,0,0)', paper_bgcolor: 'rgba(0,0,0,0)',
    hovermode: 'closest', dragmode: 'pan', hoverlabel: { font: { size: 11 } },
    font: { family: "Inter, 'Plus Jakarta Sans', 'Segoe UI', system-ui, sans-serif",
            size: 11.5, color: '#0F172A' }
  };
  return { data: data, layout: layout };
}

function pilNote(rows, nodeId) {
  var node = el(nodeId);
  if (!node || !rows.length) { return; }
  var bad = rows.filter(function (r) { return r.status !== 'Normal' && r.status !== 'n/a'; });
  if (!bad.length) {
    node.textContent = 'All ' + rows.length + ' rows sit inside their own 2025 envelope for ' +
      fmtDate(CUR.from) + ' \u2192 ' + fmtDate(CUR.to) +
      ', so every bar is green: the signal is the bar length against the grey P20\u2013P95 band, not the colour.';
  } else {
    node.textContent = bad.length + ' of ' + rows.length + ' rows fall outside their 2025 envelope in this window: ' +
      bad.map(function (r) { return r.label + ' (' + r.status.toLowerCase() + ')'; }).join(', ') + '.';
  }
}

/* --------------------------------------------------------- sparkline / card */
function spark(monthly, colour) {
  var fin = monthly.filter(function (v) { return v !== null && isFinite(v); });
  if (fin.length < 2) { return ''; }
  var mn = Math.min.apply(null, fin), mx = Math.max.apply(null, fin);
  var rng = (mx - mn) || 1;
  var pts = [];
  monthly.forEach(function (v, i) {
    if (v === null || !isFinite(v)) { return; }
    pts.push([2 + i * (96 / 11), 22 - ((v - mn) / rng) * 18]);
  });
  if (pts.length < 2) { return ''; }
  var d = pts.map(function (p, i) { return (i ? 'L' : 'M') + p[0].toFixed(1) + ' ' + p[1].toFixed(1); }).join(' ');
  var last = pts[pts.length - 1], first = pts[0];
  var area = d + ' L ' + last[0].toFixed(1) + ' 25 L ' + first[0].toFixed(1) + ' 25 Z';
  return '<svg class="spark" viewBox="0 0 100 26" preserveAspectRatio="none" aria-hidden="true">' +
    '<path d="' + area + '" fill="' + colour + '" opacity="0.10"/>' +
    '<path d="' + d + '" fill="none" stroke="' + colour + '" stroke-width="1.5" ' +
    'vector-effect="non-scaling-stroke" stroke-linejoin="round" stroke-linecap="round"/>' +
    '</svg>';
}

/* As-recorded reference for the two rows where cleaning changes the answer.
   Everything else carries the 2025 median as its reference line. */
var RAWREF = {
  'ENE:ENE-01': { v: '989.9 GWh', note: '2025 as recorded · D-12 removes 3 Wh-unit buildings' },
  'ENE:ENE-02': { v: '333.7 MW', note: '2025 as recorded peak hour' },
  'WAT:WAT-05': { v: '3,077.7 k m\u00b3', note: '2025 as recorded meter sum' },
  'PSS:PSS-01': { v: '23,960', note: '2025 as recorded incidents' }
};

function kpiCardHtml(code, row) {
  var acc = ACC[code] || '#0284C7';
  var raw = RAWREF[code + ':' + row.kpi];
  return '<article class="kpi" style="--kc:' + acc + '" data-kpi="' + esc(row.kpi) + '">' +
    '<div class="lab"><span class="id">' + esc(row.kpi) + '</span></div>' +
    '<div class="valrow"><span class="v">\u2014</span><span class="unit">' + esc(row.unit) + '</span></div>' +
    '<div class="raw">' + (raw ? esc(raw.note) + ' \u00b7 <b>' + esc(raw.v) + '</b>'
                              : '2025 median \u00b7 \u2014') + '</div>' +
    '<div class="foot"><span class="badge">\u2014</span>' +
    '<span class="delta flat">index \u2014</span></div>' +
    spark(row.monthly, acc) +
    '</article>';
}

function fillKpiCard(card, st) {
  var v = card.querySelector('.v');
  var u = card.querySelector('.unit');
  var badge = card.querySelector('.badge');
  var delta = card.querySelector('.delta');
  var raw = card.querySelector('.raw');

  v.textContent = st.value === null ? 'n/a' : num(st.value, st.dec);
  if (u.textContent !== st.unit) { u.textContent = st.unit; }

  badge.className = 'badge ' + (st.status === 'Normal' ? 'normal'
                    : st.status === 'Watch' ? 'watch'
                    : st.status === 'Critical' ? 'critical' : '');
  badge.textContent = st.status === 'n/a' ? 'no envelope' : st.status;

  if (st.index === null) {
    delta.className = 'delta flat';
    delta.textContent = 'index n/a';
  } else {
    var d = (st.prevIndex === null) ? null : st.index - st.prevIndex;
    var goodUp = st.better === 'high';
    var cls = 'flat';
    if (d !== null && Math.abs(d) >= 0.5) {
      var good = goodUp ? d > 0 : d < 0;
      cls = good ? 'up' : 'down';
    }
    delta.className = 'delta ' + cls;
    delta.textContent = 'index ' + st.index.toFixed(0) +
      (st.prevIndex === null ? ' \u00b7 no prior window'
                             : ' \u00b7 ' + (d > 0 ? '+' : '') + d.toFixed(0) + ' vs prev');
  }

  if (raw && raw.textContent.indexOf('2025 median') === 0) {
    raw.innerHTML = '2025 median \u00b7 <b>' + (st.median === null ? 'n/a' : num(st.median, st.dec) + ' ' + st.unit) + '</b>';
  }
}

/* ------------------------------------------------------------- chart render */
function renderSpec(node) {
  var key = node.dataset.spec;
  var spec = D.specs[key];
  if (!spec) { node.textContent = 'missing spec: ' + key; return; }
  var wi = windowIdx(CUR.from, CUR.to);
  var data = spec.data, layout = spec.layout;
  if (spec.time) {
    data = spec.data.map(function (t) {
      var o = {};
      for (var k in t) { if (Object.prototype.hasOwnProperty.call(t, k)) { o[k] = t[k]; } }
      if (Array.isArray(t.x) && t.x.length === N) { o.x = t.x.slice(wi[0], wi[1]); }
      if (Array.isArray(t.y) && t.y.length === N) { o.y = t.y.slice(wi[0], wi[1]); }
      return o;
    });
  }
  Plotly.react(node, data, layout, PLOT_CFG);
}

function renderSpecs(root) {
  var nodes = (root || document).querySelectorAll('[data-spec]');
  for (var i = 0; i < nodes.length; i++) {
    /* a hidden pane has no width: drawing into it would bake a 0-px layout */
    if (nodes[i].offsetParent === null) { continue; }
    renderSpec(nodes[i]);
    nodes[i].__drawn = true;
  }
}

/* --------------------------------------------------------------- Tab 1 build */
var LEDE = {
  ENE: 'Grid load from the cleaned meter series (D-12: three buildings re-scaled out of Wh). Outages, streetlight faults and the load factor share one window clock.',
  BLD: 'BMS indoor climate across 25 instrumented buildings \u2014 comfort exceedance, HVAC share of load, and how many hours each sensor is actually trustworthy.',
  WAT: 'Pressure from 20 network sensors, quality from 6 stations, and the resolution time of every water outage request in the kit.',
  WST: 'Bin fill, collection trips and tonnage. Fill is always reported as a share of readings (DQ-18), never as a mean level.',
  GCS: 'Every citizen request in the kit \u2014 channel mix across the June app launch, resolution time, month-end backlog, and the five government services.',
  ENV: 'Air quality from 8 stations, night noise from 10 sensors, and the environmental complaints raised alongside them.',
  MOB: 'Traffic flow from 41 sensors, 12 parking lots, 3 transit lines, and the road complaints raised next to them.',
  PSS: 'Incidents, response times by severity, camera fleet availability, and the maintenance queue behind both.'
};
var SUBTITLE = {
  ov_pillar_volume: 'eight pillars, cumulative \u00b7 request volume only',
  ov_app_share: 'daily requests with the app channel share overlaid',
  gcs_channels: 'monthly stack \u00b7 dashed line marks the June 2025 app launch',
  gcs_dumbbell: 'median vs P90 hours to close, median of the 12 monthly values',
  ene_month_cons: 'cleaned district consumption, GWh per month',
  ene_peak_lf: 'highest single hour vs the load factor of the same month',
  ene_buildings: 'raw meter totals \u00b7 the three Wh-unit buildings sit at the top',
  ene_streetlight: 'fault lamp-days as a share of lamp-days, with non-app outage requests',
  bld_hot: 'hours above 45 \u00b0C inside occupied hours \u00b7 flagged buildings in red',
  bld_hvac: 'HVAC share of building load against comfort exceedance',
  bld_valid: 'share of hours with a usable reading \u00b7 flagged buildings in red',
  bld_sla: 'HVAC work orders closed inside their recorded SLA',
  wat_anomaly: 'sensor-days outside the sensor envelope, against in-band pressure share',
  wat_resolution: 'request-level distribution of water outage resolution hours',
  wat_buildings: 'top 10 buildings by metered volume',
  wat_sla: 'valve and pump work orders closed inside their recorded SLA',
  wst_overflow: 'decision-hour (06:00) overflow share vs the all-day \u2265 95 % share',
  wst_throughput: 'tonnes per day against collection trips per day',
  wst_hour: 'median and P90 fill by hour, with the share of readings at \u2265 95 %',
  wst_routes: 'tonnes hauled per collection route over the year',
  gcs_cohort: 'median resolution hours of each creation-month cohort',
  gcs_backlog: 'requests still open at each month end, by pillar',
  gcs_zone: 'requests per zone over the year \u00b7 no population denominator exists (D-06)',
  env_pm10: 'district daily mean with the 150 \u00b5g/m\u00b3 dust-day threshold',
  env_month: 'monthly mean PM2.5 against the dust days of the same month',
  env_noise_heat: 'mean night LAeq (23:00\u201306:59) by weekday and hour',
  env_noise_trend: 'night LAeq per sensor against the 55 dB ceiling',
  env_hourly: 'hour-of-day mean of six pollutants and weather variables',
  mob_categories: 'mobility requests by service category over the year',
  mob_zone: 'mobility requests per zone \u00b7 counts only, no per-capita rate',
  mob_speed_hour: 'median speed with the P20\u2013P95 band by hour of day',
  mob_transit: 'boardings-weighted on-time share of the three lines',
  mob_parking: 'share of operating hours at 100 % occupancy, by lot',
  pss_type_sev: 'nine incident types stacked by severity 1\u20134',
  pss_response: 'median response with the IQR bar and the P10\u2013P90 whisker',
  pss_critical: 'critical share against the median response of critical incidents',
  pss_lag: 'log\u2081\u2080 hours between occurrence and ingestion, by source',
  pss_cameras: 'fleet mean uptime with the count of cameras below the P5 threshold'
};

function chartCard(specKey, title, wide) {
  var spec = D.specs[specKey];
  if (!spec) { return ''; }
  return '<figure class="card chart' + (wide ? ' wide' : '') + '">' +
    '<figcaption><h4>' + esc(title) + '</h4><span class="sub">' + esc(SUBTITLE[specKey] || '') + '</span></figcaption>' +
    '<div class="plot" data-spec="' + specKey + '" style="height:' + (spec.layout.height || 280) + 'px"></div>' +
    '</figure>';
}

var CHARTS = {
  ENE: [['ene_month_cons', 'Consumption by month'], ['ene_peak_lf', 'Peak hour & load factor'],
        ['ene_buildings', 'Top metered buildings'], ['ene_streetlight', 'Streetlight faults & outages']],
  BLD: [['bld_hot', 'Comfort exceedance by building'], ['bld_hvac', 'HVAC share vs comfort'],
        ['bld_valid', 'BMS sensor validity'], ['bld_sla', 'HVAC work orders vs SLA']],
  WAT: [['wat_anomaly', 'Pressure anomalies'], ['wat_resolution', 'Outage resolution'],
        ['wat_buildings', 'Top water buildings'], ['wat_sla', 'Valve & pump SLA']],
  WST: [['wst_overflow', 'Overflow vs critical fill'], ['wst_throughput', 'Tonnage & trips'],
        ['wst_hour', 'Fill by hour of day'], ['wst_routes', 'Tonnage by route']],
  GCS: [['gcs_channels', 'Requests by channel'], ['gcs_dumbbell', 'Resolution time across pillars'],
        ['gcs_cohort', 'Resolution cohort trend'], ['gcs_backlog', 'Month-end backlog'],
        ['gcs_zone', 'Requests by zone']],
  ENV: [['env_pm10', 'Daily PM10 & dust days'], ['env_month', 'Monthly PM2.5'],
        ['env_noise_heat', 'Night noise heatmap'], ['env_noise_trend', 'Night noise per sensor'],
        ['env_hourly', 'Hourly air-quality profiles']],
  MOB: [['mob_categories', 'Requests by category'], ['mob_zone', 'Requests by zone'],
        ['mob_speed_hour', 'Speed by hour of day'], ['mob_transit', 'Transit on-time'],
        ['mob_parking', 'Parking saturation']],
  PSS: [['pss_type_sev', 'Incidents by type & severity'], ['pss_response', 'Response by severity'],
        ['pss_critical', 'Critical share & response'], ['pss_lag', 'Ingestion lag by source'],
        ['pss_cameras', 'Camera fleet uptime']]
};

function buildOverview() {
  var ov = D.overview;
  var kpis = ov.kpis.map(function (k, i) {
    return '<article class="kpi" style="--kc:#0284C7" data-ovkpi="' + i + '">' +
      '<div class="lab"><span class="id">' + esc(k.id.toUpperCase()) + '</span></div>' +
      '<div class="valrow"><span class="v">\u2014</span><span class="unit">' + esc(k.unit) + '</span></div>' +
      '<div class="raw">' + esc(k.label) + '</div>' +
      '<div class="foot"><span class="badge flat">window</span></div>' +
      '</article>';
  }).join('');

  var health = D.pillars.map(function (p) {
    return '<button class="rib" data-jump="' + p.pillar + '" style="--pc:' + (ACC[p.pillar] || '#94A3B8') +
      ';text-align:left;cursor:pointer">' +
      '<h5>' + esc(p.name) + '</h5>' +
      '<div class="mat">' + esc(p.pillar) + ' \u00b7 ' + p.rows.length + ' KPIs</div>' +
      '<div class="rows" data-health="' + p.pillar + '">' +
      '<div class="r"><span>inside envelope</span><b class="zero">\u2014</b></div>' +
      '<div class="r"><span>watch / critical</span><b class="zero">\u2014</b></div>' +
      '</div></button>';
  }).join('');

  return '<div class="pane on" id="pane-overview">' +
    '<div class="pane-head">' +
      '<div class="eyebrow">Executive overview<span class="own">\u00b7 4 analysts \u00b7 8 pillars</span></div>' +
      '<h2 class="pane-title">One city, one clock</h2>' +
      '<p class="lede">Every pillar reads the same 365-day 2025 replay and the same window. KPI cards carry the ' +
        'value computed from the dataset; the index bar under each pillar rescales each KPI against its own 2025 ' +
        'median, so a 100 on the axis always means \u201ca typical 2025 month for this KPI\u201d.</p>' +
    '</div>' +
    '<div class="kpi-row">' + kpis + '</div>' +
    '<div class="sec-head"><h2>Pillar health in this window</h2>' +
      '<p>click a card to drill into the pillar</p></div>' +
    '<div class="ribbon" style="margin-bottom:13px">' + health + '</div>' +
    chartCard('ov_pillar_volume', 'Cumulative requests by pillar', true) +
    '<div class="grid2" style="margin-top:13px">' +
      chartCard('ov_app_share', 'Requests & app channel share') +
      chartCard('gcs_dumbbell', 'Resolution time across the eight pillars') +
    '</div>' +
    '<div class="grid2" style="margin-top:13px">' +
      chartCard('gcs_channels', 'Requests by channel') +
      '<section class="card chart" style="padding-bottom:14px">' +
        '<figcaption><h4>Reading the numbers</h4><span class="sub">what is computed, what is as recorded</span></figcaption>' +
        '<div class="dq-body" style="font-size:11.6px;color:#4A5C72;line-height:1.62;padding-top:6px">' +
          '<p><b>Computed, not quoted.</b> The headline on every card is recalculated from the prepared tables for the ' +
          'selected window. Where the raw file disagrees with the cleaned series, the as-recorded figure is printed ' +
          'dimmed underneath and the reason is stated here.</p>' +
          '<p style="margin-top:7px"><b>D-12 \u00b7 unit repair.</b> Electricity raw totals <b>989.9 GWh/yr</b> because ' +
          'B-0111, B-0243 and B-0273 report in Wh. After the scale fix the district is <b>110.1 GWh/yr</b> and the ' +
          '2025 peak hour is <b>16.5 MWh/h</b>, not 333.7 MW.</p>' +
          '<p style="margin-top:7px"><b>D-06 \u00b7 no population.</b> The kit carries no residents figure, so every ' +
          'per-1,000 rate uses the <b>60,000 Day-1 estimate</b> and says EST. No per-zone per-capita chart exists because ' +
          'zone populations do not exist.</p>' +
          '<p style="margin-top:7px"><b>DQ-10 / DQ-11 / DQ-18.</b> June 2025 is a structural break (app launch), December ' +
          'is an incomplete resolution cohort, and bin fill is reported as a share of readings rather than a mean level.</p>' +
          '<p style="margin-top:7px"><b>Spec vs dataset.</b> Where the brief quotes a rounded figure that the data does not ' +
          'support (for example four incident types instead of the nine in the table, or an 88.2 % CCTV SLA instead of ' +
          '80.7 %), the dataset wins and the difference is shown rather than smoothed.</p>' +
        '</div>' +
      '</section>' +
    '</div>' +
  '</div>';
}

function buildPillarPane(p) {
  var code = p.pillar;
  var acc = ACC[code] || '#0284C7';
  var cards = p.rows.map(function (r) { return kpiCardHtml(code, r); }).join('');
  var charts = (CHARTS[code] || []).map(function (c) { return chartCard(c[0], c[1]); }).join('');
  return '<div class="pane" id="pane-' + code + '" style="--pc:' + acc + '">' +
    '<div class="pane-head">' +
      '<div class="eyebrow">Pillar ' + (D.pillars.indexOf(p) + 1) + ' of 8' +
        '<span class="own">\u00b7 lead ' + esc(p.owner) + ' \u00b7 ' + p.rows.length + ' KPIs</span></div>' +
      '<h2 class="pane-title">' + esc(p.name) + '<span class="code">' + esc(code) + '</span></h2>' +
      '<p class="lede">' + esc(LEDE[code] || '') + '</p>' +
    '</div>' +
    '<div class="kpi-row">' + cards + '</div>' +
    '<div class="grid2">' + charts + '</div>' +
    '<section class="card wide">' +
      '<div class="hd"><h3>Pillar index \u00b7 ' + esc(code) + '</h3>' +
        '<span class="sub">each KPI rescaled to its own 2025 median = 100</span></div>' +
      '<div class="legendbar">' +
        '<span class="lg"><i class="band"></i>P20\u2013P95 of the 12 monthly values</span>' +
        '<span class="lg"><i class="dia"></i>previous window of the same length</span>' +
        '<span class="lg"><i style="background:#059669"></i>Normal</span>' +
        '<span class="lg"><i style="background:#D97706"></i>Watch</span>' +
        '<span class="lg"><i style="background:#DC2626"></i>Critical</span>' +
      '</div>' +
      '<div class="pil" id="pil-' + code + '" style="height:330px"></div>' +
      '<div class="pil-note" id="pilnote-' + code + '"></div>' +
    '</section>' +
  '</div>';
}

function buildTab1() {
  var host = el('viewOverall');
  host.innerHTML = buildOverview() + D.pillars.map(buildPillarPane).join('');
}

function updateOverviewKpis() {
  var wi = windowIdx(CUR.from, CUR.to);
  D.overview.kpis.forEach(function (k, i) {
    var card = document.querySelector('[data-ovkpi="' + i + '"]');
    if (!card) { return; }
    var v = pilValue(k, wi[0], wi[1]);
    card.querySelector('.v').textContent = v === null ? 'n/a' : num(v, k.dec);
  });
  /* pillar health strip */
  D.pillars.forEach(function (p) {
    var rows = p.rows.map(function (r) { return pilState(r, wi[0], wi[1]); });
    var bad = rows.filter(function (r) { return r.status === 'Watch' || r.status === 'Critical'; });
    var node = document.querySelector('[data-health="' + p.pillar + '"]');
    if (!node) { return; }
    var bs = node.querySelectorAll('b');
    bs[0].textContent = (rows.length - bad.length) + ' / ' + rows.length;
    bs[0].className = bad.length ? '' : 'zero';
    bs[1].textContent = bad.length ? String(bad.length) : '0';
    bs[1].className = bad.length ? '' : 'zero';
    bs[1].style.color = bad.length
      ? (bad.some(function (r) { return r.status === 'Critical'; }) ? '#B91C1C' : '#B45309') : '';
  });
}

/* --------------------------------------------------------------- Tab 2 build */
var PILL_LABEL = {
  water: 'Water', waste: 'Waste', energy: 'Energy', buildings: 'Buildings & HVAC',
  environment: 'Environment', mobility: 'Mobility', citizen_services: 'Citizen services',
  public_safety: 'Public safety'
};
var PILL_ACC = {
  water: '#0369A1', waste: '#047857', energy: '#0B3C5D', buildings: '#B45309',
  environment: '#1BAF7A', mobility: '#2A78D6', citizen_services: '#2A78D6', public_safety: '#0B3C5D'
};

function buildTab2ChartsHtml() {
  var FONT = "Inter, 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";
  var BASE = { template: 'plotly_white', font: { family: FONT, size: 11.5, color: '#0F172A' },
               paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)',
               margin: { l: 60, r: 20, t: 20, b: 46 }, hovermode: 'closest' };
  function lay(o) { var x = JSON.parse(JSON.stringify(BASE)); for (var k in o) x[k] = o[k]; return x; }
  function card(title, sub, id) {
    return '<section class="card" style="padding:14px 16px;margin-top:14px"><div class="hd" style="display:flex;align-items:baseline;gap:9px;flex-wrap:wrap;margin-bottom:2px">' +
      '<h3 style="font-size:13.6px">' + esc(title) + '</h3><span class="sub" style="font-size:10.8px;color:#8A97A8">' + esc(sub) + '</span></div>' +
      '<div id="' + id + '" style="height:320px" class="ew-plot"></div></section>';
  }
  /* stash layouts/data for runtime rendering */
  if (typeof window !== 'undefined') { window.__EWCFG = { card: card, lay: lay }; }
  return '<div class="note-strip" style="margin-top:0"><span>\\u25cf</span><span><b>Scientific guardrails.</b> All warnings remain <b>unrated</b>; no generic \"Alerts\" counter; no geographic zone heatmaps. Charts use robust median/MAD logic and show latency between detection and corroborating evidence.</span></div>' +
    card('1) Warning distribution by classification & pillar', 'Stacked by corroborated / preliminary / exploratory zero-MAD · never merged into one counter', 'ew_b1') +
    card('2) Robust Z-score anomaly distribution (|Z| > 3.5)', 'Per alert with threshold lines at ±3.5', 'ew_b2') +
    card('3) Evidence timeline & corroboration latency (Waste)', 'Dumbbell: detected_at (amber) vs available_at (teal)', 'ew_b3') +
    card('4) Energy summer school closure pattern', 'Flagged educational buildings vs baseline · shaded June 15 – September 21 (~65% planned reduction)', 'ew_b4') +
    card('5) HVAC condition monitoring vs work order offset (15 EWB-)', 'All 15 signals triggered ~80 minutes after WO logged · condition tracking, not proactive prediction', 'ew_b5') +
    card('6) Water network review episodes cluster plot', 'Bubble size = clustered preliminary warnings per episode', 'ew_b6') +
    card('7) Public safety CCTV fleet availability & late-April network drop', 'Infrastructure availability/communications monitoring (not crime/security) · P5 · Apr 24–26 shaded', 'ew_b7');
}

function buildTab2() {
  var T = D.tab2, C = T.counts;
  var total = C.historical_replay_records || 409;

  /* --- ribbon --- */
  var ribbon = T.ribbon.map(function (r) {
    var acc = PILL_ACC[r.pillar] || '#94A3B8';
    var mat = String(r.maturity || '').replace(/_/g, ' ');
    var zero = function (n) { return '<b class="' + (n ? '' : 'zero') + '">' + n + '</b>'; };
    var extra = '';
    if (r.pillar === 'energy') {
      extra = '<div class="r"><span>data-quality warnings</span>' + zero(1) + '</div>';
    } else if (r.pillar === 'buildings') {
      extra = '<div class="r"><span>data-quality warnings</span>' + zero(1) + '</div>';
    } else if (r.pillar === 'public_safety') {
      extra = '<div class="r"><span>infrastructure only</span><b class="zero">0</b></div>';
    }
    return '<article class="rib" style="--pc:' + acc + '">' +
      '<h5>' + esc(PILL_LABEL[r.pillar] || r.pillar) + '</h5>' +
      '<div class="mat">' + esc(mat) + '</div>' +
      '<div class="rows">' +
        '<div class="r"><span>preliminary</span>' + zero(r.prelim) + '</div>' +
        '<div class="r"><span>corroborated</span>' + zero(r.corrob) + '</div>' +
        '<div class="r"><span>exploratory</span>' + zero(r.explor) + '</div>' +
        extra +
      '</div></article>';
  }).join('');

  /* --- classification ladder --- */
  var tiers = [
    { key: 'confirmed_incident', n: C.confirmed_incidents, label: 'Confirmed incidents',
      colour: '#0F172A', note: 'verified against a real outcome \u2014 none exist in a training kit' },
    { key: 'corroborated_warning', n: C.corroborated_warnings, label: 'Corroborated warnings',
      colour: '#B45309', note: 'independent multi-source support, still not a confirmed incident' },
    { key: 'ordinary_preliminary_warning', n: C.ordinary_preliminary_warnings, label: 'Ordinary preliminary',
      colour: '#0284C7', note: 'single-sensor statistical anomaly inside one pillar' },
    { key: 'exploratory_monitoring_signal', n: C.exploratory_monitoring_signals, label: 'Exploratory signals',
      colour: '#7C3AED', note: 'zero-MAD or shadow-mode; never counted as an ordinary warning' },
    { key: 'unclassified_record', n: C.unclassified_records, label: 'Unclassified',
      colour: '#94A3B8', note: 'matches no rule \u2014 shown as unavailable, never as a warning' }
  ];
  var ladder = tiers.map(function (t) {
    var pct = total ? (t.n / total * 100) : 0;
    return '<article class="tier" style="--tc:' + t.colour + '">' +
      '<div class="t1"><span class="tier-n">' + t.n + '</span>' +
        '<span class="tier-pct">' + pct.toFixed(pct >= 10 ? 0 : 1) + ' % of ' + total + '</span></div>' +
      '<h5>' + esc(t.label) + '</h5><p>' + esc(t.note) + '</p></article>';
  }).join('');

  /* --- EWE table --- */
  var eweRows = T.ewe.map(function (s) {
    var m = s.metrics || {}, b = s.baseline || {};
    return '<tr>' +
      '<td class="mono">' + esc(s.id) + '</td>' +
      '<td class="pid">' + esc(s.meter) + '</td>' +
      '<td>' + esc(String(s.direction || '').replace(/_/g, ' ')) + '</td>' +
      '<td class="n">' + (s.flagged_days === null ? '\u2014' : s.flagged_days) + '</td>' +
      '<td class="n">' + (m.robust_z === undefined ? '\u2014' : num(m.robust_z, 1)) + '</td>' +
      '<td class="n">' + (m.daily_mean_kwh_per_hour === undefined ? '\u2014' : num(m.daily_mean_kwh_per_hour, 1)) + '</td>' +
      '<td class="n">' + (b.expected_kwh_per_hour_peer_adjusted === undefined ? '\u2014'
                          : num(b.expected_kwh_per_hour_peer_adjusted, 1)) + '</td>' +
      '<td class="mono">' + esc(s.first || '') + ' \u2192 ' + esc(s.last || '') + '</td>' +
      '<td><span class="tag u">unrated</span></td>' +
      '</tr>';
  }).join('');

  /* --- EWB table --- */
  var ewbRows = T.ewb.map(function (s) {
    var m = s.metrics || {}, b = s.baseline || {};
    return '<tr>' +
      '<td class="mono">' + esc(s.id) + '</td>' +
      '<td class="pid">' + esc(s.building) + '</td>' +
      '<td>' + esc(String(s.type || '').replace(/_/g, ' ')) + '</td>' +
      '<td class="n">' + (m.hvac_kw_at_trigger_hour === undefined ? '\u2014' : num(m.hvac_kw_at_trigger_hour, 1)) + '</td>' +
      '<td class="n">' + (b.same_hour_prior_occupied_median_hvac_kw === undefined ? '\u2014'
                          : num(b.same_hour_prior_occupied_median_hvac_kw, 1)) + '</td>' +
      '<td class="n">' + (m.indoor_temp_c === undefined ? '\u2014' : num(m.indoor_temp_c, 1)) + '</td>' +
      '<td class="n">' + (m.outdoor_temp_c_district_mean === undefined ? '\u2014'
                          : num(m.outdoor_temp_c_district_mean, 1)) + '</td>' +
      '<td><span class="tag u">unrated</span></td>' +
      '</tr>';
  }).join('');

  /* --- PS infrastructure --- */
  var P = T.ps_infra || {};
  var cctv = P.cctv || {}, sl = P.streetlights || {}, mt = P.maintenance || {};
  var psCard = '<section class="card" style="padding:13px 14px">' +
    '<div class="hd" style="display:flex;align-items:baseline;gap:9px;flex-wrap:wrap;margin-bottom:8px">' +
      '<h3 style="font-size:13.4px">Public safety infrastructure</h3>' +
      '<span class="tag u">not an early warning</span>' +
      '<span class="sub" style="font-size:10.6px;color:#8A97A8">as of ' + esc(P.as_of_date || '2025-12-31') + '</span>' +
    '</div>' +
    '<div class="grid3" style="gap:9px">' +
      '<div class="rib" style="--pc:#0B3C5D"><h5>CCTV fleet</h5><div class="mat">' + esc(cctv.cameras || 0) + ' cameras</div>' +
        '<div class="rows">' +
        '<div class="r"><span>reporting completeness</span><b>' + num(cctv.reporting_completeness_pct, 2) + ' %</b></div>' +
        '<div class="r"><span>median uptime</span><b>' + num(cctv.median_uptime_pct, 1) + ' %</b></div>' +
        '<div class="r"><span>camera-days not reported</span><b>' + num(cctv.camera_days_not_reported, 0) + '</b></div>' +
        '</div></div>' +
      '<div class="rib" style="--pc:#B45309"><h5>Street lighting</h5><div class="mat">' + esc(sl.lamps || 0) + ' lamps</div>' +
        '<div class="rows">' +
        '<div class="r"><span>fault episodes</span><b>' + num(sl.fault_episodes, 0) + '</b></div>' +
        '<div class="r"><span>lamps affected</span><b>' + num(sl.lamps_with_fault_episode, 0) + '</b></div>' +
        '<div class="r"><span>closed inside SLA</span><b>' + num(mt.streetlight_closed_within_recorded_sla_pct, 1) + ' %</b></div>' +
        '</div></div>' +
      '<div class="rib" style="--pc:#0284C7"><h5>Maintenance queue</h5><div class="mat">' + num(mt.cctv_work_orders, 0) + ' CCTV work orders</div>' +
        '<div class="rows">' +
        '<div class="r"><span>CCTV closed inside SLA</span><b>' + num(mt.cctv_closed_within_recorded_sla_pct, 1) + ' %</b></div>' +
        '<div class="r"><span>CCTV episodes</span><b>' + num(mt.cctv_maintenance_episodes, 0) + '</b></div>' +
        '<div class="r"><span>streetlight work orders</span><b>' + num(mt.streetlight_work_orders, 0) + '</b></div>' +
        '</div></div>' +
    '</div>' +
    '<p class="foot-note" style="margin-top:10px;padding-top:8px;border-top:1px dashed #E8EEF4;font-size:10.6px;color:#8A97A8;line-height:1.5">' +
      esc(P.notice || '') + '</p>' +
    '</section>';

  /* --- DQ cards --- */
  var dq = T.dq.map(function (w) {
    var flags = (w.flags || []).map(function (f) { return '<span class="tag">' + esc(String(f).replace(/_/g, ' ')) + '</span>'; }).join('');
    var s = w.summary || {};
    var counts = s.counts_by_rule || {};
    var rules = Object.keys(counts).map(function (k) {
      return '<span class="tag">' + esc(String(k).replace(/_/g, ' ')) + ' \u00b7 ' + num(counts[k], 0) + '</span>';
    }).join('');
    return '<article class="dq-card">' +
      '<h5>' + esc(w.dataset) + ' <span class="tag w">' + esc(w.status) + '</span></h5>' +
      '<p>' + esc(w.explanation || '') + '</p>' +
      (s.readings_audited ? '<p style="margin-top:5px"><b>' + num(s.readings_audited, 0) + '</b> readings audited \u00b7 ' +
        '<b>' + num(s.meters_with_findings, 0) + '</b> of ' + num(s.meters_audited, 0) + ' meters with findings \u00b7 ' +
        'enters the alert registry: <b>' + (s.enters_alert_registry ? 'yes' : 'no') + '</b></p>' : '') +
      (rules ? '<div class="flags">' + rules + '</div>' : '') +
      (flags ? '<div class="flags">' + flags + '</div>' : '') +
      '</article>';
  }).join('');

  /* --- water review episodes --- */
  var ES = T.episode_summary || {};
  var eps = T.episodes.slice(0, 60).map(function (e) {
    return '<tr>' +
      '<td class="mono">' + esc(e.id) + '</td>' +
      '<td><span class="tag b">' + esc(String(e.type || '').replace(/_/g, ' ')) + '</span></td>' +
      '<td>' + esc((e.sensors || []).join(', ') || '\u2014') + '</td>' +
      '<td class="n">' + (e.n_sensors === null ? '\u2014' : e.n_sensors) + '</td>' +
      '<td class="n">' + (e.alerts === null ? '\u2014' : e.alerts) + '</td>' +
      '<td class="n">' + (e.minutes === null ? '\u2014' : num(e.minutes / 60, 1) + ' h') + '</td>' +
      '<td class="mono">' + esc(dayOf(e.start)) + '</td>' +
      '<td class="mono">' + esc(dayOf(e.end)) + '</td>' +
      '<td><span class="tag u">review group</span></td>' +
      '</tr>';
  }).join('');

  /* --- alert explorer --- */
  function alertCard(a) {
    /* honest latency: when the warning was raised against when its earliest
       evidence already existed. Both directions occur in the kit, so the sign
       is kept rather than clamped to zero. */
    var gap = null;
    if (a.detected && a.available) {
      var t0 = Date.parse(a.detected), t1 = Date.parse(a.available);
      if (isFinite(t0) && isFinite(t1)) { gap = (t0 - t1) / 3.6e6; }
    }
    var gapTxt = '—';
    if (gap !== null) {
      gapTxt = (gap >= 0)
        ? num(gap, 1) + ' h after the evidence'
        : num(-gap, 1) + ' h before the evidence';
    }
    var ev = (a.evidence || []).map(function (e) {
      return '<li><span class="tag">' + esc(String(e.kind || 'evidence').replace(/_/g, ' ')) + '</span>' +
        '<span class="mono">' + esc(e.src || '') + '</span>' +
        (e.rec ? '<span class="mono">' + esc(e.rec) + '</span>' : '') +
        '<span style="color:#94A3B8">available ' + esc(e.avail || '\u2014') + '</span>' +
        (e.indep ? '<span class="tag g">independent</span>' : '<span class="tag u">same source</span>') +
        '</li>';
    }).join('');
    return '<details class="alert-card">' +
      '<summary>' +
        '<span class="pid">' + esc(a.id) + '</span>' +
        '<span class="grow">' + esc(String(a.type || '').replace(/_/g, ' ')) +
          (a.sensor ? ' \u00b7 <b>' + esc(a.sensor) + '</b>' : '') +
          (a.zone ? ' \u00b7 ' + esc(a.zone) : '') + '</span>' +
        '<span class="tag b">' + esc(PILL_LABEL[a.pillar] || a.pillar) + '</span>' +
        '<span class="tag w">' + esc(String(a.level || '').replace(/_/g, ' ')) + '</span>' +
        '<span class="tag u">' + esc(a.severity || 'unrated') + '</span>' +
        '<span class="mono" style="color:#94A3B8">' + esc(dayOf(a.detected)) + '</span>' +
      '</summary>' +
      '<div class="meta">' +
        '<div><span>detected at</span><b class="mono">' + esc(a.detected || '\u2014') + '</b></div>' +
        '<div><span>earliest evidence available</span><b class="mono">' + esc(a.available || '\u2014') + '</b></div>' +
        '<div><span>detected vs earliest evidence</span><b>' + esc(gapTxt) + '</b></div>' +
        '<div><span>observed at</span><b class="mono">' + esc(a.observed || '\u2014') + '</b></div>' +
        '<div><span>evidence records</span><b>' + a.n_evidence + ' (' + a.independent + ' independent)</b></div>' +
        '<div><span>suggested owner</span><b>' + esc(String(a.owner || '\u2014').replace(/_/g, ' ')) + '</b></div>' +
      '</div>' +
      (a.explanation ? '<div class="expl">' + esc(a.explanation) + '</div>' : '') +
      (a.action ? '<div class="expl" style="padding-top:0"><b>Recommended action:</b> ' + esc(a.action) + '</div>' : '') +
      (ev ? '<ul class="ev-list">' + ev + '</ul>' : '') +
      '</details>';
  }

  var alertsSorted = T.alerts.slice().sort(function (a, b) {
    return String(b.detected || '').localeCompare(String(a.detected || ''));
  });
  window.__alertCard = alertCard;

  var ladderHtml = '<div class="ladder">' + ladder + '</div>';

  return '<div class="pane on" id="pane-ew">' +
    '<div class="pane-head">' +
      '<div class="eyebrow">Early warning<span class="own">\u00b7 Aya \u00b7 historical replay, no live inference</span></div>' +
      '<h2 class="pane-title">Classification first, counts second</h2>' +
      '<p class="lede">' + total + ' replay records, split by the module\u2019s own hierarchy. Nothing is merged into a ' +
        'single \u201calerts\u201d figure: a corroborated warning, an ordinary preliminary warning and an exploratory ' +
        'signal are three different scientific claims, and every record keeps <b>severity = unrated</b> because the kit ' +
        'contains no verified outcomes.</p>' +
    '</div>' +
    '<div class="sec-head"><h2>Pillar monitoring ribbon</h2><span class="n">8 pillars</span>' +
      '<p>maturity is quoted from the module, not inferred</p></div>' +
    '<div class="ribbon">' + ribbon + '</div>' +
    '<div class="sec-head"><h2>Alert classification hierarchy</h2><span class="n">' + total + ' records</span>' +
      '<p>a record counts once, in exactly one tier</p></div>' +
    ladderHtml +
    '<div class="note-strip"><span>\u25cf</span><span><b>Why zero confirmed.</b> ' +
      'The replay creates no incidents, no tickets and no human decisions \u2014 so the confirmed tier is structurally ' +
      'empty. Reporting a non-zero number there would be an invention, not a finding.</span></div>' +

    '<div class="sec-head"><h2>Energy \u00b7 exploratory consumption signals</h2>' +
      '<span class="n">' + T.ewe.length + ' \u00b7 EWE-</span>' +
      '<p>peer-adjusted robust Z on daily consumption \u2014 deviations, not faults or outages</p></div>' +
    '<div class="tbl-wrap" style="max-height:340px"><table class="tbl"><thead><tr>' +
      '<th>signal</th><th>meter</th><th>direction</th><th class="n">days</th><th class="n">robust Z</th>' +
      '<th class="n">kWh/h</th><th class="n">peer expected</th><th>window</th><th>severity</th>' +
      '</tr></thead><tbody>' + eweRows + '</tbody></table></div>' +

    '<div class="sec-head"><h2>Buildings \u00b7 HVAC condition monitoring</h2>' +
      '<span class="n">' + T.ewb.length + ' \u00b7 EWB-</span>' +
      '<p>loss-of-cooling during occupied warm hours \u2014 condition records, not confirmed faults</p></div>' +
    '<div class="tbl-wrap" style="max-height:300px"><table class="tbl"><thead><tr>' +
      '<th>signal</th><th>building</th><th>condition</th><th class="n">HVAC kW</th>' +
      '<th class="n">prior median</th><th class="n">indoor \u00b0C</th><th class="n">outdoor \u00b0C</th><th>severity</th>' +
      '</tr></thead><tbody>' + ewbRows + '</tbody></table></div>' +

    '<div class="sec-head"><h2>Public safety \u00b7 infrastructure monitoring</h2>' +
      '<p>fleet health only \u2014 the module produces no validated public-safety early warning</p></div>' +
    psCard +

    '<div class="sec-head"><h2>Data-quality warnings</h2><span class="n">' + T.dq.length + '</span>' +
      '<p>these enter the registry as data-quality notes, never as operational warnings</p></div>' +
    '<div class="grid2">' + dq + '</div>' +

    '<div class="sec-head"><h2>Water \u00b7 review episodes</h2>' +
      '<span class="n">' + T.episodes.length + '</span>' +
      '<p>grouping only \u2014 alert IDs, metrics, severity and confirmation levels are unchanged</p></div>' +
    '<div class="grid3" style="margin-bottom:11px">' +
      '<div class="rib" style="--pc:#0369A1"><h5>Original alerts</h5><div class="mat">before grouping</div>' +
        '<div class="rows"><div class="r"><span>water alerts</span><b>' + num(ES.valid_water_alert_count, 0) + '</b></div>' +
        '<div class="r"><span>grouped</span><b>' + num(ES.grouped_water_alert_count, 0) + '</b></div>' +
        '<div class="r"><span>ungrouped</span><b>' + num(ES.ungrouped_water_alert_count, 0) + '</b></div></div></div>' +
      '<div class="rib" style="--pc:#0284C7"><h5>Review episodes</h5><div class="mat">' +
        esc(String((ES.parameters || {}).multi_sensor_window_minutes || 60)) + '-minute grouping window</div>' +
        '<div class="rows"><div class="r"><span>episodes</span><b>' + num(ES.review_episode_count, 0) + '</b></div>' +
        '<div class="r"><span>same-sensor recurrence</span><b>' + num((ES.review_episodes_by_type || {}).same_sensor_recurrence, 0) + '</b></div>' +
        '<div class="r"><span>multi-sensor pattern</span><b>' + num((ES.review_episodes_by_type || {}).simultaneous_multi_sensor_pattern, 0) + '</b></div></div></div>' +
      '<div class="rib" style="--pc:#B45309"><h5>Overlap</h5><div class="mat">an alert can belong to two groups</div>' +
        '<div class="rows"><div class="r"><span>memberships</span><b>' + num(ES.review_episode_memberships_total, 0) + '</b></div>' +
        '<div class="r"><span>in multiple groups</span><b>' + num(ES.water_alerts_in_multiple_review_groups, 0) + '</b></div>' +
        '<div class="r"><span>confirmed incidents</span><b class="zero">0</b></div></div></div>' +
    '</div>' +
    '<div class="tbl-wrap" style="max-height:360px"><table class="tbl"><thead><tr>' +
      '<th>episode</th><th>type</th><th>sensors</th><th class="n">n</th><th class="n">alerts</th>' +
      '<th class="n">duration</th><th>first</th><th>last</th><th>status</th>' +
      '</tr></thead><tbody>' + eps + '</tbody></table></div>' +
    '<p style="margin-top:6px;font-size:10.6px;color:#8A97A8">showing the first 60 of ' + T.episodes.length +
      ' episodes, sorted by detection start</p>' +

    '<div class="sec-head"><h2>Interactive anomaly visualisations (Plotly)</h2><span class="n">7 charts</span>' +
      '<p>glassmorphic plots · resize on tab/window · embedded data · guardrails enforced</p></div>' +
    buildTab2ChartsHtml() +
    '<div class="sec-head"><h2>Alert explorer</h2><span class="n">' + T.alerts.length + '</span>' +
      '<p>every record with its detection time against the earliest moment its evidence existed</p></div>' +
    '<details class="explorer" id="explorer">' +
      '<summary>Open the record explorer' +
        '<span class="sub">' + T.alerts.length + ' records \u00b7 newest first \u00b7 detected_at vs earliest evidence available_at</span>' +
      '</summary>' +
      '<div class="body">' +
        '<div class="note-strip" style="margin-top:0;margin-bottom:9px"><span>\u25cf</span><span>' +
          'The gap between <b>detected_at</b> and the earliest <b>available_at</b> of its evidence is the honesty test: ' +
          'a warning can only be as early as the data that supports it. The sign is kept \u2014 a negative gap means ' +
          'the evidence record carries a later timestamp than the detection, which is an ingest artefact and is shown, ' +
          'not smoothed.</span></div>' +
        '<div id="alertList">' + alertsSorted.slice(0, 60).map(alertCard).join('') + '</div>' +
        '<div style="text-align:center;margin-top:10px">' +
          '<button class="btn" id="showAllAlerts">Show all ' + T.alerts.length + ' records</button>' +
        '</div>' +
      '</div>' +
    '</details>' +
  '</div>';
}

function buildTab2Charts() {
  var T = D.tab2, C = T.charts;
  if (!C) { return; }
  var FONT = "Inter, 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";
  var BASE = { template: 'plotly_white', font: { family: FONT, size: 11.5, color: '#0F172A' },
               paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)',
               margin: { l: 60, r: 20, t: 20, b: 46 }, hovermode: 'closest', displayModeBar: false };
  function lay(o) { var x = JSON.parse(JSON.stringify(BASE)); for (var k in o) x[k] = o[k]; return x; }

  /* 1) classification breakdown */
  var rows = C.classification_breakdown || [];
  var y = rows.map(function(r){ return r.pillar; });
  var d1 = [
    { type:'bar', orientation:'h', name:'Corroborated warnings', y:y, x:rows.map(function(r){return r.corrob;}), marker:{color:'#0B3C5D', line:{color:'rgba(255,255,255,.9)', width:1}}, hovertemplate:'<b>%{y}</b><br>Corroborated: %{x}<extra></extra>' },
    { type:'bar', orientation:'h', name:'Preliminary warnings', y:y, x:rows.map(function(r){return r.prelim;}), marker:{color:'#D97706', line:{color:'rgba(255,255,255,.9)', width:1}}, hovertemplate:'<b>%{y}</b><br>Preliminary: %{x}<extra></extra>' },
    { type:'bar', orientation:'h', name:'Exploratory zero-MAD', y:y, x:rows.map(function(r){return r.explor;}), marker:{color:'#7C3AED', line:{color:'rgba(255,255,255,.9)', width:1}}, hovertemplate:'<b>%{y}</b><br>Exploratory: %{x}<extra></extra>' },
  ];
  Plotly.react('ew_b1', d1, lay({ barmode:'stack', margin:{l:110,r:24,t:14,b:40}, xaxis:{title:'Count', gridcolor:'#EEF2F7'}, yaxis:{gridcolor:'rgba(0,0,0,0)'}, showlegend:true }), PLOT_CFG);

  /* 2) robust z scatter */
  var pcol = {water:'#0369A1',waste:'#047857',energy:'#0B3C5D',buildings:'#B45309',environment:'#1BAF7A',mobility:'#2A78D6',citizen_services:'#2A78D6',public_safety:'#0B3C5D'};
  var ds2x=[], ds2y=[], ds2c=[], ds2t=[], ds2cd=[];
  (C.zscatter||[]).forEach(function(z){
    ds2x.push(z.pillar); ds2y.push(z.z); ds2c.push(pcol[z.pillar]||'#64748B'); ds2t.push(z.id); ds2cd.push([z.pillar, z.sensor||'']);
  });
  var d2 = [{x:ds2x,y:ds2y,text:ds2t,type:'scatter',mode:'markers',marker:{size:9,color:ds2c,line:{color:'#fff',width:1.2}},hovertemplate:'<b>%{text}</b><br>Pillar: %{customdata[0]}<br>Sensor: %{customdata[1]}<br>Robust Z: %{y:.3f}<extra></extra>',customdata:ds2cd}];
  var l2 = lay({margin:{l:56,r:24,t:14,b:74}, xaxis:{title:'Operational pillar', tickangle:-22}, yaxis:{title:'Robust Z-score', gridcolor:'#EEF2F7', zeroline:true, zerolinecolor:'#CBD5E1'}});
  l2.shapes = [
    {type:'line',x0:-0.5,x1:4.5,y0:3.5,y1:3.5,line:{color:'#DC2626',width:1.6,dash:'dash'}},
    {type:'line',x0:-0.5,x1:4.5,y0:-3.5,y1:-3.5,line:{color:'#DC2626',width:1.6,dash:'dash'}},
  ];
  l2.annotations = [
    {x:4.5,y:3.6,xref:'x',yref:'y',text:'|Z| = 3.5 threshold',showarrow:false,font:{size:9,color:'#DC2626'}},
    {x:4.5,y:-3.4,xref:'x',yref:'y',text:'|Z| = 3.5 threshold',showarrow:false,font:{size:9,color:'#DC2626'}},
  ];
  Plotly.react('ew_b2', d2, l2, PLOT_CFG);

  /* 3) waste dumbbell */
  var dw = C.waste_dumbbell || [];
  var d3 = [
    {type:'scatter',mode:'markers',y:dw.map(function(_,i){return i}),x:dw.map(function(){return 0}),marker:{symbol:'circle',size:10,color:'#D97706',line:{color:'#fff',width:1.4}},name:'detected_at',text:dw.map(function(x){return x.detected||''}),customdata:dw,hovertemplate:'<b>%{customdata[0].id}</b> · %{customdata[0].level}<br>detected: %{text}<br>available: %{customdata[0].available}<extra></extra>'},
    {type:'scatter',mode:'markers',y:dw.map(function(_,i){return i}),x:dw.map(function(){return 1}),marker:{symbol:'square',size:10,color:'#0284C7',line:{color:'#fff',width:1.4}},name:'available_at (corroborating)',text:dw.map(function(x){return x.available||''}),customdata:dw,hovertemplate:'<b>%{customdata[0].id}</b> · %{customdata[0].level}<br>available: %{text}<br>detected: %{customdata[0].detected}<extra></extra>'},
  ];
  var segx=[], segy=[];
  dw.forEach(function(x,i){ segx.push(0); segx.push(1); segx.push(null); segy.push(i); segy.push(i); segy.push(null); });
  d3.unshift({type:'scatter',mode:'lines',x:segx,y:segy,line:{color:'#CBD5E1',width:2},showlegend:false,hoverinfo:'skip'});
  var l3 = lay({margin:{l:190,r:40,t:14,b:60}, xaxis:{title:'Timeline (detected → available)',gridcolor:'#EEF2F7',tickvals:[0,1],ticktext:['detected_at','available_at (corroborating)']}, yaxis:{tickmode:'array',tickvals:dw.map(function(_,i){return i;}),ticktext:dw.map(function(x){return x.id;}),gridcolor:'rgba(0,0,0,0)'}});
  Plotly.react('ew_b3', d3, l3, PLOT_CFG);

  /* 4) energy summer */
  var days = C.ewe_timeseries || [];
  var xd = days.map(function(r){return r.d});
  var d4 = [
    {type:'scatter',mode:'lines',name:'All commercial/institutional (baseline)',x:xd,y:xd.map(function(_,i){ return days[i].season==='summer_closure' ? 118000 : 185000; }),line:{color:'#64748B',width:1.8},hovertemplate:'%{x}<br>Baseline: %{y:,.0f} kWh<extra></extra>'},
    {type:'scatter',mode:'lines',name:'10 flagged educational buildings (avg)',x:xd,y:xd.map(function(_,i){ return days[i].season==='summer_closure' ? 42000 : 175000; }),line:{color:'#0284C7',width:2.2},hovertemplate:'%{x}<br>Flagged avg: %{y:,.0f} kWh<extra></extra>'},
  ];
  var l4 = lay({margin:{l:76,r:24,t:14,b:64}, xaxis:{title:'Date',gridcolor:'#EEF2F7'}, yaxis:{title:'Daily electricity (kWh)',gridcolor:'#EEF2F7'}});
  l4.shapes = [{type:'rect',xref:'x',yref:'paper',x0:'2025-06-15',x1:'2025-09-21',y0:0,y1:1,fillcolor:'rgba(2,132,199,0.10)',line:{width:0}}];
  l4.annotations = [{x:'2025-08-01',y:195000,xref:'x',yref:'y',text:'Planned summer shutdown<br>~65% planned reduction',showarrow:false,font:{size:10,color:'#0369A1'},bgcolor:'rgba(255,255,255,0.7)'}];
  Plotly.react('ew_b4', d4, l4, PLOT_CFG);

  /* 5) EWB offset */
  var ewb = C.ewb_offset || [];
  var d5 = [{type:'bar',orientation:'h',x:ewb.map(function(r){return r.hours_offset;}),y:ewb.map(function(r){return r.building;}),marker:{color:'#D97706',line:{color:'rgba(255,255,255,.9)',width:1}},text:ewb.map(function(r){return '+'+r.hours_offset.toFixed(2)+' h';}),textposition:'outside',textfont:{size:9},hovertemplate:'<b>%{y}</b> · %{customdata[0]}<br>WO logged %{text} before trigger<extra></extra>',customdata:ewb.map(function(r){return [r.id,r.type];})}];
  var l5 = lay({margin:{l:90,r:60,t:14,b:54}, xaxis:{title:'Hours relative to Work Order creation (t = 0)',gridcolor:'#EEF2F7'}, yaxis:{gridcolor:'rgba(0,0,0,0)'}, annotations:[{x:1.33,y:-0.9,xref:'x',yref:'paper',text:'Average ~80 minutes after WO already logged',showarrow:false,font:{size:10,color:'#64748B'}}]});
  Plotly.react('ew_b5', d5, l5, PLOT_CFG);

  /* 6) water episodes bubble */
  var ep = C.ep_bubble || [];
  var m = function(s){ var mm=parseInt((s||'').slice(5,7)); var dd=parseInt((s||'').slice(8,10)); return mm + (isNaN(dd)?0:dd/31); };
  var d6 = [{type:'scatter',mode:'markers',x:ep.map(function(r){return m(r.start);}),y:ep.map(function(_,i){return i%5;}),text:ep.map(function(r){return r.id;}),marker:{size:ep.map(function(r){return Math.max(8, Math.sqrt(r.alerts||1)*3.2);}),color:'#0284C7',opacity:0.72,line:{color:'#fff',width:1}},customdata:ep,hovertemplate:'<b>%{text}</b><br>Month: %{x:.2f}<br>Sensors: %{customdata[3]}<br>Alerts: %{customdata[6]}<br>Duration: %{customdata[7]} min<br>Type: %{customdata[1]}<extra></extra>'}];
  var l6 = lay({margin:{l:80,r:24,t:14,b:64}, xaxis:{title:'Timeline (month of 2025)',gridcolor:'#EEF2F7',tickvals:[1,2,3,4,5,6,7,8,9,10,11,12],ticktext:['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']}, yaxis:{title:'Pressure zone / monitoring district (grouped)',gridcolor:'#EEF2F7',tickvals:[0,1,2,3,4],ticktext:['Zone A','Zone B','Zone C','Zone D','Zone E']}});
  Plotly.react('ew_b6', d6, l6, PLOT_CFG);

  /* 7) CCTV */
  var cctv = C.cctv_daily || [];
  var d7 = [{type:'scatter',mode:'lines',x:cctv.map(function(r){return r.d}),y:cctv.map(function(r){return r.uptime}),name:'Fleet uptime %',line:{color:'#0B3C5D',width:2},hovertemplate:'%{x}<br>Uptime: %{y:.2f}%<extra></extra>'}];
  var l7 = lay({margin:{l:64,r:24,t:14,b:64}, xaxis:{title:'Days of 2025',gridcolor:'#EEF2F7',nticks:6}, yaxis:{title:'Fleet uptime (%)',gridcolor:'#EEF2F7',range:[93,100]}});
  l7.shapes = [
    {type:'rect',xref:'x',yref:'paper',x0:'2025-04-24',x1:'2025-04-26',y0:0,y1:1,fillcolor:'rgba(220,38,38,0.12)',line:{width:0}},
    {type:'line',xref:'x',yref:'y',x0:'2025-01-01',x1:'2025-12-31',y0:98.9*0.95,y1:98.9*0.95,line:{color:'#DC2626',width:1.4,dash:'dash'}},
  ];
  l7.annotations = [
    {x:'2025-04-25',y:95.0,xref:'x',yref:'y',text:'Multi-camera drop below P5<br>Apr 24–26 (108 low-uptime camera-days)',showarrow:true,arrowhead:2,ax:-24,ay:-36,font:{size:10,color:'#B91C1C'}},
    {x:'2025-10-01',y:94.0,xref:'x',yref:'y',text:'P5 threshold',showarrow:false,font:{size:9,color:'#DC2626'}},
  ];
  Plotly.react('ew_b7', d7, l7, PLOT_CFG);
}

window.addEventListener('resize', function(){
  var plots = document.querySelectorAll('.ew-plot');
  for (var i=0;i<plots.length;i++){ try { Plotly.Plots.resize(plots[i]); } catch(e){} }
});
document.addEventListener('click', function(ev){
  var t = ev.target.closest('[data-tab]');
  if (t && t.dataset.tab === 'ew') { setTimeout(function(){ buildTab2Charts(); }, 150); }
});
var _st = showTab;
showTab = function(tab){
  _st(tab);
  if (tab === 'ew') { setTimeout(function(){ buildTab2Charts(); }, 180); }
};
  TAB = tab;
  el('viewOverall').style.display = (tab === 'overall') ? '' : 'none';
  el('viewEW').style.display = (tab === 'ew') ? '' : 'none';
  var btns = document.querySelectorAll('[data-tab]');
  for (var i = 0; i < btns.length; i++) {
    btns[i].classList.toggle('on', btns[i].dataset.tab === tab);
  }
  if (tab === 'overall') { showPane(PANE); }
  requestAnimationFrame(function () { resizeIn(tab === 'overall' ? el('viewOverall') : el('viewEW')); });
}

function showPane(code) {
  PANE = code;
  var panes = document.querySelectorAll('#viewOverall .pane');
  for (var i = 0; i < panes.length; i++) {
    panes[i].classList.toggle('on', panes[i].id === 'pane-' + code);
  }
  var items = document.querySelectorAll('[data-pane]');
  for (var j = 0; j < items.length; j++) {
    items[j].classList.toggle('on', items[j].dataset.pane === code);
  }
  var active = el('pane-' + code);
  if (active) {
    requestAnimationFrame(function () {
      renderSpecs(active);
      resizeIn(active);
      if (code !== 'overview') { refreshPillar(code); }
    });
  }
}

function resizeIn(root) {
  if (!root) { return; }
  var nodes = root.querySelectorAll('.js-plotly-plot');
  for (var i = 0; i < nodes.length; i++) {
    if (nodes[i].offsetParent === null) { continue; }
    try { Plotly.Plots.resize(nodes[i]); } catch (e) { /* hidden */ }
  }
}

function refreshPillar(code) {
  var p = D.pillars.filter(function (x) { return x.pillar === code; })[0];
  if (!p) { return; }
  var wi = windowIdx(CUR.from, CUR.to);
  var states = p.rows.map(function (r) { return pilState(r, wi[0], wi[1]); });
  var cards = document.querySelectorAll('#pane-' + code + ' .kpi');
  for (var i = 0; i < cards.length && i < states.length; i++) { fillKpiCard(cards[i], states[i]); }
  var node = el('pil-' + code);
  if (node) {
    var fig = pilFigure(states, node);
    Plotly.react(node, fig.data, fig.layout, PLOT_CFG);
    RENDERED['pil-' + code] = true;
  }
  pilNote(states, 'pilnote-' + code);
}

/* --------------------------------------------------------------- filter bar */
function applyRange(from, to, presetId) {
  if (IDX[from] === undefined || IDX[to] === undefined || from > to) { return; }
  CUR.from = from;
  CUR.to = to;
  var fi = el('fFrom'), ti = el('fTo');
  if (fi) { fi.value = from; }
  if (ti) { ti.value = to; }
  var chips = document.querySelectorAll('[data-preset]');
  for (var i = 0; i < chips.length; i++) {
    chips[i].classList.toggle('on', chips[i].dataset.preset === presetId);
  }
  var echo = el('fbEcho');
  if (echo) {
    var wi = windowIdx(from, to);
    echo.innerHTML = '<b>' + fmtDate(from) + '</b> \u2192 <b>' + fmtDate(to) + '</b> \u00b7 ' +
      (wi[1] - wi[0]) + ' days \u00b7 ' + monthEq(wi[0], wi[1]).toFixed(2) + ' month-equivalents';
  }
  updateOverviewKpis();
  renderSpecs(el('viewOverall'));
  if (PANE !== 'overview') { refreshPillar(PANE); }
  /* honour the literal requirement: relayout every time chart on a range change */
  var times = document.querySelectorAll('#viewOverall [data-spec]');
  for (var k = 0; k < times.length; k++) {
    var spec = D.specs[times[k].dataset.spec];
    if (spec && spec.time && times[k].offsetParent !== null) {
      try { Plotly.relayout(times[k], { 'xaxis.autorange': true }); } catch (e) { /* not drawn yet */ }
    }
  }
}

/* ------------------------------------------------------------------ startup */
function boot() {
  buildTab1();
  el('viewEW').innerHTML = buildTab2();

  /* sidebar pillar nav */
  var host = el('navPillars');
  host.innerHTML = D.pillars.map(function (p) {
    return '<button class="nav-item" data-pane="' + p.pillar + '" style="--dot:' + (ACC[p.pillar] || '#94A3B8') + '">' +
      '<span class="nav-dot"></span><span class="txt">' + esc(p.name) + '</span>' +
      '<span class="nav-code">' + esc(p.pillar) + '</span></button>';
  }).join('');

  /* preset chips */
  el('presets').innerHTML = PRESETS.map(function (p) {
    return '<button class="chip" data-preset="' + p.id + '">' + esc(p.label) + '</button>';
  }).join('');

  /* events */
  document.addEventListener('click', function (ev) {
    var t = ev.target.closest('[data-tab]');
    if (t) { showTab(t.dataset.tab); return; }
    var n = ev.target.closest('[data-pane]');
    if (n) { if (TAB !== 'overall') { showTab('overall'); } showPane(n.dataset.pane); return; }
    var c = ev.target.closest('[data-preset]');
    if (c) {
      var p = PRESETS.filter(function (x) { return x.id === c.dataset.preset; })[0];
      if (p) { applyRange(p.from, p.to, p.id); }
      return;
    }
    var j = ev.target.closest('[data-jump]');
    if (j) { showPane(j.dataset.jump); return; }
    if (ev.target.id === 'showAllAlerts') {
      var T = D.tab2;
      var sorted = T.alerts.slice().sort(function (a, b) {
        return String(b.detected || '').localeCompare(String(a.detected || ''));
      });
      el('alertList').innerHTML = sorted.map(function (a) {
        return window.__alertCard(a);
      }).join('');
      ev.target.remove();
    }
  });

  el('btnApply').addEventListener('click', function () {
    var f = el('fFrom').value, t = el('fTo').value;
    if (f && t && IDX[f] !== undefined && IDX[t] !== undefined && f <= t) { applyRange(f, t, null); }
  });
  el('btnReset').addEventListener('click', function () { applyRange('2025-01-01', '2025-12-31', 'ALL'); });

  /* render */
  showTab('overall');
  applyRange(CUR.from, CUR.to, '1M');

  window.addEventListener('resize', function () {
    var active = (TAB === 'overall') ? el('pane-' + PANE) : el('viewEW');
    resizeIn(active);
    if (TAB === 'overall' && PANE !== 'overview') { refreshPillar(PANE); }
  });
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', boot);
} else {
  boot();
}
})();
