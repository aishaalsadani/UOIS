/* Pure, DOM-free logic for the Complaint Verification viewer (Phase 4A.1).
 * Loaded by viewer.html as window.CVLogic and unit-tested with Node (module.exports).
 * It filters, selects and orders records; it never changes an assessment.
 */
(function (root) {
  "use strict";

  const EMPTY_FILTERS = Object.freeze({ category: "", status: "", safety: "", action: "", group: "" });
  const TIMELINE_LIMIT = 28;
  // Timeline row priority: decisive first, then context, then not-available reasons, then excluded.
  const TIMELINE_ORDER = ["supporting", "contradicting", "contextual", "uncertain", "unknown", "later", "excluded"];

  function emptyFilters() { return Object.assign({}, EMPTY_FILTERS); }
  function recordId(r, mode) { return mode === "A" ? r.request_id : r.scenario_id; }
  function assessmentOf(r, mode, time) { return mode === "A" ? r.assessments[time] : r.assessment; }
  function groupOf(r, mode) { return mode === "A" ? r.stratum : String(r.scenario_id).split("_")[0]; }
  function categoryOf(r, mode) { return mode === "A" ? r.category_id : (r.category_ids || []).join(" / "); }

  function matches(r, mode, time, filters, search) {
    const a = assessmentOf(r, mode, time);
    const rec = a && a.recommendation;
    const f = filters || EMPTY_FILTERS;
    if (f.category && categoryOf(r, mode) !== f.category) return false;
    if (f.status && String(a.status) !== f.status) return false;
    if (f.group && groupOf(r, mode) !== f.group) return false;
    if (mode === "A") {
      if (f.safety && (rec ? rec.safety.level : "") !== f.safety) return false;
      if (f.action && (rec ? rec.primary_action : "") !== f.action) return false;
    }
    const q = String(search || "").trim().toLowerCase();
    if (!q) return true;
    return [recordId(r, mode), r.request_id, r.text, r.zone_reported, r.purpose, categoryOf(r, mode)]
      .join(" ").toLowerCase().includes(q);
  }

  function filterRecords(records, mode, time, filters, search) {
    return records.filter(r => matches(r, mode, time, filters, search));
  }

  /* The selected record must always be one of the visible (filtered) records.
   * Keep the current one if still visible, else the preferred default, else the first; null if none. */
  function resolveSelection(visibleIds, currentId, preferredId) {
    if (currentId && visibleIds.includes(currentId)) return currentId;
    if (preferredId && visibleIds.includes(preferredId)) return preferredId;
    return visibleIds.length ? visibleIds[0] : null;
  }

  /* Switching mode resets search and filters: Mode A and Mode B never share records or filter values. */
  function stateForMode(data, mode) {
    const records = mode === "A" ? data.mode_a.records : data.mode_b.scenarios;
    const ids = records.map(r => recordId(r, mode));
    const preferred = mode === "A" ? data.default_complaint : null;
    return { mode, search: "", filters: emptyFilters(), interp: 0, selected: resolveSelection(ids, null, preferred) };
  }

  function availabilityState(e) {
    if (e.availability_state) return e.availability_state;
    if (e.role !== "unavailable") return "";
    const codes = e.reason_codes || [];
    if (codes.includes("available_after_as_of")) return "later";
    if (codes.includes("availability_uncertain_at_as_of")) return "uncertain";
    return "unknown";
  }

  function timelineBucket(e) {
    return e.group === "unavailable" ? availabilityState(e) || "unknown" : e.group;
  }

  /* Which evidence rows the timeline draws, with an explicit count of what is omitted. */
  function timelineSelection(interpretation, limit) {
    const cap = limit || TIMELINE_LIMIT;
    const all = [];
    for (const items of Object.values(interpretation.groups || {})) {
      for (const e of items) if (e.time && e.time.first_observed_utc) all.push(e);
    }
    const rank = e => TIMELINE_ORDER.indexOf(timelineBucket(e));
    const ordered = all.slice().sort((a, b) => rank(a) - rank(b) || (b.counted - a.counted));
    const shown = ordered.slice(0, cap);
    const omittedByBucket = {};
    for (const e of ordered.slice(cap)) {
      const k = timelineBucket(e);
      omittedByBucket[k] = (omittedByBucket[k] || 0) + 1;
    }
    let withoutTime = 0;
    for (const items of Object.values(interpretation.groups || {})) {
      for (const e of items) if (!(e.time && e.time.first_observed_utc)) withoutTime += 1;
    }
    return {
      shown, total: all.length, omitted: all.length - shown.length, omittedByBucket, withoutTime,
      truncatedObservations: shown.filter(e => e.time.observations_truncated)
        .map(e => ({ evidence_id: e.evidence_id, shown: e.time.observations.length, total: e.time.observation_count })),
    };
  }

  const api = { EMPTY_FILTERS, TIMELINE_LIMIT, emptyFilters, recordId, assessmentOf, groupOf, categoryOf, matches,
    filterRecords, resolveSelection, stateForMode, availabilityState, timelineBucket, timelineSelection };
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.CVLogic = api;
})(typeof window !== "undefined" ? window : globalThis);
