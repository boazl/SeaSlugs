/* The dive trip's "summary trip" field (DiveTripAdmin, SummaryTripSelect): a long list of trips, narrowed by three
 * filters built from the options' own data -- country, region and year. Options that do not match are hidden and
 * disabled (as in divetrip_admin.js); the chosen trip always stays visible. */
(function () {
  document.addEventListener('DOMContentLoaded', function () {
    var select = document.getElementById('id_summary_trip');
    if (!select || select.disabled) return;
    var options = Array.prototype.slice.call(select.options).filter(function (o) { return o.value; });
    var keys = [['country', 'ארץ'], ['region', 'אזור'], ['year', 'שנה']];
    var bar = document.createElement('div');
    bar.className = 'summary-trip-filters';
    bar.style.cssText = 'display:flex;flex-wrap:wrap;gap:8px;margin:0 0 6px';
    var filters = {};
    keys.forEach(function (pair) {
      var key = pair[0], values = {};
      options.forEach(function (o) { var v = o.dataset[key]; if (v) values[v] = o.dataset[key + 'Label'] || v; });
      var filter = document.createElement('select');
      filter.setAttribute('aria-label', pair[1]);
      filter.appendChild(new Option(pair[1] + ': הכול', ''));
      Object.keys(values).sort(function (a, b) {
        return key === 'year' ? b - a : values[a].localeCompare(values[b], 'he');
      }).forEach(function (v) { filter.appendChild(new Option(values[v], v)); });
      filter.addEventListener('change', apply);
      filters[key] = filter;
      bar.appendChild(filter);
    });
    select.parentNode.insertBefore(bar, select);
    function apply() {
      options.forEach(function (o) {
        var hidden = keys.some(function (pair) {
          var want = filters[pair[0]].value;
          return want && o.dataset[pair[0]] !== want;
        }) && !o.selected;
        o.hidden = hidden;
        o.disabled = hidden;
      });
    }
  });
})();
