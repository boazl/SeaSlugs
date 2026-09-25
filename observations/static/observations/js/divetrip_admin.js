/* DiveTripAdmin: the "sea" field is only meaningful when no region is chosen -- once a
 * region is set, its own sea is used automatically (see DiveTrip.resolved_sea). Hide the
 * row while a region is selected so the form doesn't show two ways to say the same thing,
 * same idea as the site/site_other toggle on the public observation form (form.html). */
(function () {
  function toggleSeaRow() {
    var region = document.getElementById('id_region');
    var seaRow = document.querySelector('.field-sea');
    if (!region || !seaRow) return;
    seaRow.style.display = region.value ? 'none' : '';
  }
  document.addEventListener('DOMContentLoaded', function () {
    var region = document.getElementById('id_region');
    if (region) region.addEventListener('change', toggleSeaRow);
    toggleSeaRow();
  });
})();
