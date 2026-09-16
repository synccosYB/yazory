(() => {
  'use strict';

  const printButton = document.querySelector('#print-application-button');
  if (!printButton) return;

  printButton.addEventListener('click', () => {
    window.print();
  });
})();
