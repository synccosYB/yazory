document.querySelectorAll('[data-sponsor-carousel]').forEach((carousel) => {
  const list = carousel.querySelector('.public-sponsor-logos');
  const previous = carousel.querySelector('.public-sponsor-previous');
  const next = carousel.querySelector('.public-sponsor-next');
  const dots = carousel.querySelector('.public-sponsor-dots');
  const sponsors = [...list.children];
  if (!sponsors.length) return;

  // Shuffle once per visit so the same sponsors do not always receive the first position.
  for (let index = sponsors.length - 1; index > 0; index -= 1) {
    const random = new Uint32Array(1);
    crypto.getRandomValues(random);
    const swap = random[0] % (index + 1);
    [sponsors[index], sponsors[swap]] = [sponsors[swap], sponsors[index]];
  }
  sponsors.forEach((sponsor) => list.append(sponsor));

  let page = 0;
  let timer;
  const pageSize = () => window.matchMedia('(max-width: 620px)').matches ? 1
    : window.matchMedia('(max-width: 980px)').matches ? 2
      : Number(carousel.dataset.pageSize || 4);
  const pageCount = () => Math.ceil(sponsors.length / pageSize());

  const render = () => {
    const size = pageSize();
    page %= pageCount();
    sponsors.forEach((sponsor, index) => {
      sponsor.hidden = index < page * size || index >= (page + 1) * size;
    });
    dots.replaceChildren(...Array.from({ length: pageCount() }, (_, index) => {
      const dot = document.createElement('button');
      dot.type = 'button';
      dot.className = 'public-sponsor-dot';
      dot.ariaLabel = `${index + 1}`;
      dot.ariaCurrent = index === page ? 'true' : 'false';
      dot.addEventListener('click', () => { page = index; render(); restart(); });
      return dot;
    }));
    const hasMultiplePages = pageCount() > 1;
    previous.hidden = next.hidden = dots.hidden = !hasMultiplePages;
  };
  const restart = () => {
    clearInterval(timer);
    if (pageCount() > 1 && !window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      timer = setInterval(() => { page = (page + 1) % pageCount(); render(); }, 7000);
    }
  };
  previous.addEventListener('click', () => { page = (page - 1 + pageCount()) % pageCount(); render(); restart(); });
  next.addEventListener('click', () => { page = (page + 1) % pageCount(); render(); restart(); });
  carousel.addEventListener('mouseenter', () => clearInterval(timer));
  carousel.addEventListener('mouseleave', restart);
  carousel.addEventListener('focusin', () => clearInterval(timer));
  carousel.addEventListener('focusout', restart);
  window.addEventListener('resize', () => { page = 0; render(); restart(); });
  render();
  restart();
});
