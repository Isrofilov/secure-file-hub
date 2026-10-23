// Applies the saved theme before the first paint to avoid a flash of the wrong colors.
(function () {
  try {
    var theme = localStorage.getItem('theme');
    if (theme === 'light' || theme === 'dark') document.documentElement.dataset.theme = theme;
  } catch (e) { /* storage unavailable */ }
})();
