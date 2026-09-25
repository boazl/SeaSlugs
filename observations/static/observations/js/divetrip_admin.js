/* DiveTripAdmin cascading fields:
 * - "sea" is only meaningful when no region is chosen -- once a region is set, its own sea
 *   is used automatically (see DiveTrip.resolved_sea). Hide the row while a region is
 *   selected so the form doesn't show two ways to say the same thing.
 * - "region" is narrowed to the selected country and/or sea (whichever is already set).
 * - "site" (reused from the existing Site table instead of a separate reserve table) is
 *   narrowed to the selected region.
 * Same idea as the site/site_other toggle and the trip-form region filter already used on
 * the public site (observations/form.html): hide+disable non-matching <option>s rather than
 * re-fetching the list, and clear the child field if its current value no longer matches. */
(function () {
  function toggleSeaRow() {
    var region = document.getElementById('id_region');
    var seaRow = document.querySelector('.field-sea');
    if (!region || !seaRow) return;
    seaRow.style.display = region.value ? 'none' : '';
  }

  function filterOptions(select, matches, reset) {
    if (!select) return;
    for (var i = 0; i < select.options.length; i++) {
      var option = select.options[i];
      if (!option.value) continue;
      var hidden = !matches(option.value);
      option.hidden = hidden;
      option.disabled = hidden;
    }
    if (reset && select.selectedOptions[0] && select.selectedOptions[0].disabled) select.value = '';
  }

  document.addEventListener('DOMContentLoaded', function () {
    var region = document.getElementById('id_region');
    var country = document.getElementById('id_country');
    var sea = document.getElementById('id_sea');
    var site = document.getElementById('id_site');

    if (region) region.addEventListener('change', toggleSeaRow);
    toggleSeaRow();

    if (!region && !site) return; // nothing left needs the fetched data

    fetch('/admin/observations/divetrip-locations/')
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        if (!data) return;

        function updateRegions(reset) {
          var countryValue = country ? country.value : '';
          var seaValue = sea ? sea.value : '';
          filterOptions(region, function (id) {
            var row = data.regions.find(function (x) { return String(x.id) === id; });
            if (!row) return true;
            if (countryValue && String(row.country_id) !== countryValue) return false;
            if (seaValue && String(row.sea_id) !== seaValue) return false;
            return true;
          }, reset);
        }

        function updateSites(reset) {
          var regionValue = region ? region.value : '';
          filterOptions(site, function (id) {
            if (!regionValue) return true;
            var row = data.sites.find(function (x) { return String(x.id) === id; });
            return !!row && String(row.region_id) === regionValue;
          }, reset);
        }

        if (country) country.addEventListener('change', function () { updateRegions(true); });
        if (sea) sea.addEventListener('change', function () { updateRegions(true); });
        updateRegions(false);

        if (region) region.addEventListener('change', function () { updateSites(true); });
        updateSites(false);
      });
  });
})();
