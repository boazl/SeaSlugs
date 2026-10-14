// A search box above the defining-sample select (admin of orders / families / genera / species in
// areas): typing narrows the list to the options containing every typed word, case-insensitively.
// The options themselves come from the server already restricted and in alphabetical order.
document.addEventListener('DOMContentLoaded', function () {
  document.querySelectorAll('select[name="defining_sample"]').forEach(function (select) {
    var input = document.createElement('input');
    input.type = 'search';
    input.placeholder = 'חיפוש דגימה…';
    input.autocomplete = 'off';
    input.style.cssText = 'display:block;margin-bottom:6px;width:min(100%,28em)';
    var count = document.createElement('span');
    count.style.cssText = 'margin-inline-start:8px;color:var(--body-quiet-color,#888)';
    select.parentNode.insertBefore(input, select);
    input.after(count);
    input.addEventListener('input', function () {
      var words = input.value.trim().toLowerCase().split(/\s+/).filter(Boolean), shown = 0, first = null;
      Array.prototype.forEach.call(select.options, function (option) {
        var match = !option.value || words.every(function (w) { return option.text.toLowerCase().indexOf(w) !== -1; });
        option.hidden = !match;
        if (match && option.value) { shown++; if (!first) first = option; }
      });
      count.textContent = words.length ? shown + ' תוצאות' : '';
      // the chosen value stays as it was unless it no longer matches -- then the first match is chosen
      var current = select.options[select.selectedIndex];
      if (words.length && first && current && current.hidden) select.value = first.value;
    });
    input.addEventListener('keydown', function (e) { if (e.key === 'Enter') e.preventDefault(); });
  });
});
