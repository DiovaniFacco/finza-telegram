(function () {
  const root = document.documentElement;
  const button = document.getElementById('theme-toggle');
  if (button) {
    button.addEventListener('click', () => {
      const isDark = root.classList.toggle('dark');
      localStorage.setItem('theme', isDark ? 'dark' : 'light');
    });
  }
})();

window.formatBRL = function (value) {
  const n = Number(value || 0);
  return new Intl.NumberFormat('pt-BR', {
    style: 'currency',
    currency: 'BRL',
    maximumFractionDigits: 2,
  }).format(n);
};

window.formatINR = window.formatBRL;

window.chartTextColor = function () {
  return document.documentElement.classList.contains('dark') ? '#E5E7EB' : '#1F2937';
};

window.chartGridColor = function () {
  return document.documentElement.classList.contains('dark')
    ? 'rgba(255,255,255,0.08)'
    : 'rgba(0,0,0,0.06)';
};
