/* DiveTripAdmin cascading fields:
 * - "region" is narrowed to the selected country (a trip's sea is its region's sea).
 * - "site" (reused from the existing Site table instead of a separate reserve table) is
 *   narrowed to the selected region.
 * Same idea as the site/site_other toggle and the trip-form region filter already used on
 * the public site (observations/form.html): hide+disable non-matching <option>s rather than
 * re-fetching the list, and clear the child field if its current value no longer matches. */
(function () {
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
    var site = document.getElementById('id_site');

    if (!region && !site) return; // nothing left needs the fetched data

    fetch('/admin/observations/divetrip-locations/')
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        if (!data) return;

        function updateRegions(reset) {
          var countryValue = country ? country.value : '';
          filterOptions(region, function (id) {
            var row = data.regions.find(function (x) { return String(x.id) === id; });
            if (!row) return true;
            if (countryValue && String(row.country_id) !== countryValue) return false;
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
        updateRegions(false);

        if (region) region.addEventListener('change', function () { updateSites(true); });
        updateSites(false);
      });
  });
})();
