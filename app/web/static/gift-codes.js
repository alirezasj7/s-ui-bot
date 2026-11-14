/* Gift-code forms: show the fields of the chosen kind and toggle the inline editors. */
(function () {
  'use strict';

  function syncKind(form, select) {
    // The enhanced dropdown fires `change` before it refreshes its hidden
    // mirror input, so read the native select itself when there is one.
    const kind = select ? select.value : form.elements.kind.value;
    form.querySelectorAll('[data-gift-kind]').forEach(function (section) {
      const visible = section.dataset.giftKind === kind;
      section.hidden = !visible;
      section.querySelectorAll('input, select').forEach(function (input) {
        input.disabled = !visible;
        if (input.hasAttribute('data-gift-required')) input.required = visible;
      });
    });
  }

  function bindForm(form) {
    const select = form.querySelector('[data-gift-kind-select]');
    if (select) select.addEventListener('change', function () { syncKind(form, select); });
    syncKind(form, select);
    const first = form.elements.first_purchase_only;
    if (first) {
      first.addEventListener('change', function () {
        if (!first.checked) return;
        form.querySelectorAll('input[name="purchase_types"]').forEach(function (input) {
          input.checked = input.value === 'new';
        });
      });
    }
  }

  function bindEditToggle(button) {
    button.addEventListener('click', function () {
      const row = document.getElementById(button.dataset.giftEdit);
      if (!row) return;
      row.hidden = !row.hidden;
      if (!row.hidden) row.scrollIntoView({ block: 'start' });
      document
        .querySelectorAll('[data-gift-edit="' + button.dataset.giftEdit + '"]')
        .forEach(function (toggle) { toggle.setAttribute('aria-expanded', String(!row.hidden)); });
    });
  }

  document.querySelectorAll('.gift-code-form').forEach(bindForm);
  document.querySelectorAll('[data-gift-edit]').forEach(bindEditToggle);
})();
