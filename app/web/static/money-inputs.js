/* Group monetary inputs without converting integer strings to floating point. */
(function (root) {
  "use strict";

  function groupMoneyDigits(value) {
    const text = String(value == null ? "" : value);
    const match = /^([+-]?)(\d+)(\.\d*)?$/.exec(text);
    if (!match) return text;
    return match[1] + match[2].replace(/\B(?=(\d{3})+(?!\d))/g, ",") + (match[3] || "");
  }

  function formatMoneyInput(input, normalize) {
    const value = input.value;
    const start = input.selectionStart;
    const end = input.selectionEnd;
    const next = groupMoneyDigits(normalize(value));
    if (next === value) return;
    const caret = (position) => {
      const length = normalize(value.slice(0, position)).length;
      let seen = 0;
      let index = 0;
      while (index < next.length && seen < length) {
        if (next[index] !== ",") seen++;
        index++;
      }
      return index;
    };
    input.value = next;
    if (start != null && end != null) {
      input.setSelectionRange(caret(start), caret(end));
    }
  }

  function syncMoneyMode(input, normalize) {
    const name = input.dataset.moneyKind;
    // The native select has the current value during capture and form resets; its mirror may lag.
    const kind = input.form && (Array.from(input.form.elements).find((control) =>
      control.tagName === "SELECT" && (control.name || control.dataset.uiSelectName) === name
    ) || input.form.elements.namedItem(name));
    const isMoney = !!kind && kind.value === input.dataset.moneyValue;
    input.toggleAttribute("data-money", isMoney);
    if (isMoney) formatMoneyInput(input, normalize);
    else input.value = normalize(input.value);
  }

  const helpers = {groupMoneyDigits, formatMoneyInput, syncMoneyMode};
  if (typeof module === "object" && module.exports) module.exports = helpers;
  else root.PanelMoney = helpers;
})(typeof window === "object" ? window : globalThis);
